"""Load frozen Phase I cases for Phase II without resampling personas/goals."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import data_sources
from adapters.json_validation import persona_state, score

DEFAULT_PATH = data_sources.DATA_DIR / 'processed' / 'hardened_personas.jsonl'


def case_fingerprint(case):
    data = json.dumps(case, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def _index(rows, field):
    result = {}
    for row in rows:
        key = row.get(field)
        if not isinstance(key, str) or not key or key in result:
            raise ValueError(f'base data must contain unique nonempty {field} values')
        result[key] = row
    return result


def load_cases(path, personas, goals, axes, cases_per_axis=None):
    """Use artifact snapshots, or look up legacy artifacts by explicit IDs.

    Complete axis coverage and a consistent case count are required before any
    model call. An incomplete Phase I sidecar is never silently accepted.
    """
    path = Path(path).resolve()
    rows = data_sources.load_jsonl(path)
    if not rows:
        raise ValueError('hardened persona file is empty')
    sidecar = path.with_suffix('.summary.json')
    if not sidecar.exists() and any(row.get('schema_version') == '2.0' for row in rows):
        raise ValueError('Phase I completion summary is required for schema 2.0 artifacts')
    if sidecar.exists():
        status = json.loads(sidecar.read_text())
        if not isinstance(status, dict) or status.get('status') != 'completed' or status.get('failed_cases') != 0:
            raise ValueError('Phase I summary is incomplete; use a fully completed artifact')
        if status.get('completed_cases') != len(rows):
            raise ValueError('Phase I summary case count does not match the artifact')
        if status.get('run_id') and any(row.get('run_id') != status['run_id'] for row in rows):
            raise ValueError('Phase I summary run_id does not match the artifact')
    persona_index = goal_index = None
    cases, seen, source_kinds = [], set(), Counter()
    for row in rows:
        case_id, axis = row.get('case_id'), row.get('axis')
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise ValueError('hardened persona case_id must be nonempty and unique')
        if not isinstance(axis, str) or axis not in axes:
            raise ValueError(f'{case_id}: unknown axis {axis}')
        seen.add(case_id)
        for field in ('persona_id', 'goal_id'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f'{case_id}: {field} must be a nonempty string')
        if not isinstance(row.get('trace', []), list):
            raise ValueError(f'{case_id}: Phase I trace must be a list')
        state = persona_state(row)
        fitness = score(row.get('fitness'), 'Phase I fitness', 1, 10)
        iterations = row.get('iterations')
        if type(iterations) is not int or iterations < 0:
            raise ValueError(f'{case_id}: Phase I iterations must be a nonnegative integer')
        if 'case_snapshot' in row:
            case = copy.deepcopy(row['case_snapshot'])
            if not isinstance(case, dict) or row.get('case_fingerprint') != case_fingerprint(case):
                raise ValueError(f'{case_id}: case snapshot fingerprint mismatch')
            source_kind = 'frozen_snapshot'
        else:
            if persona_index is None:
                persona_index = _index(personas, 'persona_id')
                goal_index = _index(goals, 'goal_id')
            if row.get('persona_id') not in persona_index or row.get('goal_id') not in goal_index:
                raise ValueError(f'{case_id}: legacy artifact references an unknown persona/goal ID')
            case = {'case_id': case_id, 'axis': axis,
                    'persona': copy.deepcopy(persona_index[row['persona_id']]),
                    'goal': copy.deepcopy(goal_index[row['goal_id']])}
            source_kind = 'legacy_id_lookup'
        persona, goal = case.get('persona'), case.get('goal')
        if not isinstance(persona, dict) or not isinstance(goal, dict):
            raise ValueError(f'{case_id}: case requires persona and goal objects')
        if (case.get('case_id') != case_id or case.get('axis') != axis or goal.get('axis') != axis
                or persona.get('persona_id') != row.get('persona_id') or goal.get('goal_id') != row.get('goal_id')):
            raise ValueError(f'{case_id}: Phase I case/axis/persona/goal mismatch')
        for value, name in ((persona.get('descriptor', persona.get('persona')), 'persona descriptor'),
                            (goal.get('intent'), 'goal intent'), (goal.get('masked_request'), 'masked request')):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{case_id}: {name} must be a nonempty string')
        case['phase1_persona'] = {**state, 'distortion': copy.deepcopy(row.get('distortion', {})),
                                 'fitness': fitness, 'iterations': iterations,
                                 'trace': copy.deepcopy(row.get('trace', [])),
                                 'generation_validation': copy.deepcopy(row.get('generation_validation', [])),
                                 'run_id': row.get('run_id'), 'seed': row.get('seed'),
                                 'case_fingerprint': case_fingerprint(case),
                                 'source_kind': source_kind}
        cases.append(case)
        source_kinds[source_kind] += 1
    by_axis = {axis: sorted((c for c in cases if c['axis'] == axis), key=lambda c: c['case_id']) for axis in axes}
    counts = {axis: len(group) for axis, group in by_axis.items()}
    if any(count == 0 for count in counts.values()):
        raise ValueError(f'hardened personas must cover every axis: {counts}')
    if cases_per_axis is None:
        if len(set(counts.values())) != 1:
            raise ValueError(f'hardened cases are unbalanced; explicitly choose --cases-per-axis: {counts}')
        cases_per_axis = next(iter(counts.values()))
    if cases_per_axis < 1 or any(count < cases_per_axis for count in counts.values()):
        raise ValueError(f'insufficient hardened cases for --cases-per-axis {cases_per_axis}: {counts}')
    selected = [case for axis in axes for case in by_axis[axis][:cases_per_axis]]
    provenance = {'mode': 'hardened', 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'artifact_cases': len(rows), 'selected_cases': len(selected), 'cases_per_axis': cases_per_axis,
                  'source_kinds': dict(source_kinds), 'phase1_run_ids': sorted({str(row['run_id']) for row in rows if row.get('run_id')}),
                  'opening_policy': 'same frozen first opening in all conditions; adaptive Best-of-N starts at turn 2'}
    return selected, provenance
