# Testing Patterns

**Analysis Date:** 2026-03-25

## Test Framework

**Runner:**
- No formal test framework detected (no pytest, unittest, nose configuration files)
- No `pytest.ini`, `setup.cfg`, `pyproject.toml`, or `tox.ini` found
- No `tests/` or `test_*` directories exist

**Assertion Library:**
- Python built-in `assert` statements used inline in pipeline scripts
- No third-party assertion library (pytest assertions, etc.)

**Run Commands:**
```bash
# No formal test runner configured
# Individual modules self-test via __main__ blocks:
python ETA-Model/src/model.py         # Tests model forward pass and save/load
python ETA-Model/src/features.py      # Tests feature extraction with mock data
python ETA-Model/src/loss.py          # Tests loss functions with scenario data
python ETA-Model/src/history_buffer.py # Tests buffer behavior
python ETA-Model/src/distance.py      # Tests distance calculation
python ETA-Model/src/inference.py     # Tests inference wrapper

# Data validation script:
python ETA-Model/scripts/validate_data.py --data-dir ./processed_data_v11

# Distance debugging function (not a test runner):
# test_distance_calculation() in ETA-Model/src/data_prep_optimized.py
```

## Test File Organization

**Location:**
- No co-located `.test.py` or `.spec.py` files
- Two types of verification exist:
  1. `if __name__ == '__main__':` blocks at the bottom of source modules (inline self-tests)
  2. Inline `assert` statements within data pipeline scripts to catch data integrity regressions

**Naming:**
- `_test.py` suffix used for one-off integration experiments: `Code/pushing_data_to_db_test.py`, `Code/simplepbtest.py`
- `validate_data.py` in `ETA-Model/scripts/` is the closest to a formal test/validation script
- Debug utilities named `debug_*.py`: `ETA-Model/src/debug_predictions.py`

**Structure:**
```
tiger-transit-app/
├── Code/
│   ├── pushing_data_to_db_test.py     # Manual integration test (Supabase insert)
│   └── simplepbtest.py               # Manual protobuf parsing test
├── ETA-Model/
│   ├── scripts/
│   │   └── validate_data.py          # Structured data validation runner
│   └── src/
│       ├── model.py                  # __main__ block: forward pass + save/load
│       ├── features.py               # __main__ block: mock telemetry extraction
│       ├── loss.py                   # __main__ block: loss scenario comparison
│       ├── history_buffer.py         # __main__ block: buffer add/compute test
│       ├── distance.py               # __main__ block: GTFS distance check
│       └── inference.py              # __main__ block: inference wrapper test
└── scripts/
    ├── build_baselines.py            # Inline assert: row count integrity checks
    ├── build_differentiator_features.py  # Inline assert: merge safety checks
    ├── build_features.py             # Inline assert: merge row explosion guard
    └── build_stop_sequences.py       # Inline assert: result shape/nullness checks
```

## Test Structure

**Inline Self-Test Pattern (`__main__` blocks):**
```python
if __name__ == '__main__':
    # Fix random seed for reproducibility
    torch.manual_seed(42)

    # Construct minimal inputs
    num_features = 32
    batch_size = 16
    features = torch.randn(batch_size, num_features)
    vehicle_ids = torch.randint(0, 50, (batch_size,))

    # Exercise the unit under test
    model = ETAPredictor(num_features=num_features, num_vehicle_ids=50)
    predictions = model(features, vehicle_ids)

    # Print results for visual inspection (no assertions)
    print(f"Output shape: {predictions.shape}")
    print(f"Sample predictions (seconds): {predictions[0].detach().numpy()}")
```
All `__main__` blocks in `ETA-Model/src/` use `torch.manual_seed(42)` or equivalent for determinism.

**Data Integrity Assert Pattern (pipeline scripts):**
```python
n_before = len(df)
df = df.merge(other_df, on='key', how='left')
assert len(df) == n_before, (
    f"Row explosion on merge: {n_before} -> {len(df)}"
)
```
This pattern appears 15+ times across `scripts/build_baselines.py`, `scripts/build_differentiator_features.py`, `scripts/build_features.py`, and `scripts/build_stop_sequences.py`.

**Structured Validation Pattern (`validate_data.py`):**
```python
@dataclass
class ValidationFinding:
    category: str
    check_name: str
    severity: Severity       # IntEnum: CRITICAL, HIGH, MEDIUM, LOW, INFO
    message: str
    affected_count: int
    total_count: int
    recommendation: str

class DistanceValidator:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.findings: list[ValidationFinding] = []

    def check_haversine_fallback_zeros(self) -> ValidationFinding:
        # Check specific data quality invariant
        ...
```
Located at `ETA-Model/scripts/validate_data.py`.

**Patterns:**
- Setup: seed RNG, construct minimal tensors or DataFrames
- Teardown: None (no cleanup)
- Assertion: visual `print()` inspection in `__main__` blocks; `assert` in pipeline scripts

## Mocking

**Framework:** None

**Patterns:**
- Mock data constructed inline using `torch.randn(...)`, `torch.randint(...)`, hardcoded dicts
- No `unittest.mock`, `pytest-mock`, or `MagicMock` usage detected
- Integration paths (GTFS files, telemetry JSONL) are accessed directly from disk in all test scenarios

**What to Mock (if tests are added):**
- File I/O: JSONL telemetry loading, Parquet reading, checkpoint save/load
- External APIs: ETA SPOT socket connection in `batchCollector.js`
- `torch.cuda.is_available()` for device selection in training scripts

**What NOT to Mock:**
- Core tensor operations and PyTorch module forward passes — these run on CPU in all self-tests
- Pandas DataFrame operations — pipeline scripts test on actual sample data

## Fixtures and Factories

**Test Data (inline construction):**
```python
# Typical mock telemetry packet (ETA-Model/src/features.py __main__)
mock_telemetry = {
    'ts': int(datetime(2025, 10, 22, 8, 30).timestamp() * 1000),
    'vid': 'jAUnt 1',
    'lt': 32.605,
    'ln': -85.485,
    'v': 15,
    'h': 90,
    'load': 5,
    'serviceState': {
        'rID': 24,
        'patternID': 1234,
        'tripID': '1895',
        'nextStopPercentProgress': 0.5,
    },
    'lastStop': {'stopID': 181, 'time': timestamp - 60000, 'onTime': -30},
    'eta': {'stopID': 152, 'seta': 300, 'eta': 290},
}
```

**Location:**
- No separate fixtures directory; all mock data is inline in `__main__` blocks
- Common seed: `torch.manual_seed(42)` and `np.random.seed(42)` for deterministic tests

## Coverage

**Requirements:** None enforced — no coverage tooling configured

**View Coverage:**
```bash
# Not configured; would require: pip install pytest-cov
# pytest --cov=ETA-Model/src --cov-report=html
```

## Test Types

**Unit Tests:**
- `__main__` blocks in `ETA-Model/src/*.py` serve as lightweight unit smoke-tests
- Test one module in isolation: model forward pass, loss computation, feature extraction, distance calculation
- No assertions — rely on visual output inspection or absence of exceptions

**Integration Tests:**
- `Code/pushing_data_to_db_test.py`: manual Supabase insert test (requires live local Supabase)
- `ETA-Model/scripts/validate_data.py`: runs structured validation against processed parquet files

**Pipeline Integrity Tests (inline asserts):**
- `scripts/build_baselines.py`: 8+ asserts guarding DataFrame row counts after every merge
- `scripts/build_differentiator_features.py`: 7+ asserts guarding merge integrity and column presence
- `scripts/build_stop_sequences.py`: asserts on `stop_progress`, null checks, `max_shape_dist > 0`

**E2E Tests:** Not present — no end-to-end test pipeline configured

## Common Patterns

**Deterministic Testing:**
```python
# Always set seeds before constructing test tensors
torch.manual_seed(42)
np.random.seed(42)
```

**Scenario-Based Loss Verification:**
```python
# ETA-Model/src/loss.py __main__ block pattern
pred_over = torch.tensor([[300.0, 400.0, 500.0]])
actual_over = torch.tensor([[200.0, 300.0, 400.0]])
loss_over = loss_fn(pred_over, actual_over)

pred_under = torch.tensor([[200.0, 300.0, 400.0]])
actual_under = torch.tensor([[300.0, 400.0, 500.0]])
loss_under = loss_fn(pred_under, actual_under)

print(f"Overestimate is {loss_over.item() / loss_under.item():.1f}x worse (target: ~5x)")
```

**Model Save/Load Round-Trip:**
```python
# ETA-Model/src/model.py __main__ block pattern
save_model(model, '/tmp/test_model.pt', {'test': True})
loaded = load_model('/tmp/test_model.pt')

with torch.no_grad():
    orig_out = model(features, vehicle_ids)
    loaded_out = loaded(features, vehicle_ids)
    diff = (orig_out - loaded_out).abs().max()
    print(f"Max difference after load: {diff.item():.6f}")
```

**Data Pipeline Row-Count Guard:**
```python
# Pattern in scripts/build_baselines.py, build_differentiator_features.py
n_before = len(df)
df = df.merge(other_df, on=key_col, how='left')
assert len(df) == n_before, (
    f"Row explosion on {merge_name} merge: {n_before} -> {len(df)}"
)
```

---

*Testing analysis: 2026-03-25*
