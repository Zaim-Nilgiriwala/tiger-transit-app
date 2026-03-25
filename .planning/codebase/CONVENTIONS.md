# Coding Conventions

**Analysis Date:** 2026-03-25

## Naming Patterns

**Files:**
- `snake_case` for all Python modules: `train_baseline.py`, `build_features.py`, `data_quality.py`
- Descriptive verbs for script files: `parse_telemetry.py`, `build_differentiator_features.py`, `explode_rows.py`
- Versioned variants use `_v2`, `_v1_1` suffixes: `build_differentiator_features.py`, `evaluate_v1_1.py`
- Optimized variants use `_optimized` suffix: `data_prep_optimized.py`

**Classes:**
- `PascalCase`: `ETAPredictor`, `AsymmetricETALoss`, `DataPipeline`, `VehicleHistoryBuffer`, `ValidationFinding`
- Descriptive full names, no abbreviations: `ETAPredictorWithUncertainty`, `LightweightETAPredictor`
- Dataclasses used for config and results: `FeatureConfig`, `NormalizationStats`, `ValidationFinding`

**Functions:**
- `snake_case` for all functions: `extract_temporal_features`, `compute_rolling_features`, `time_based_split`
- Verb-first naming for actions: `build_`, `load_`, `compute_`, `extract_`, `create_`, `generate_`
- Private helpers prefixed with `_`: `_build_encoder`, `_init_weights`, `_ordering_penalty`, `_save_outputs`

**Variables and Constants:**
- `UPPER_SNAKE_CASE` for module-level constants: `CORE_FEATURES`, `ROLLING_WINDOWS`, `PARAMS`, `NUM_BOOST_ROUND`
- `snake_case` for all local and instance variables: `train_loader`, `val_loader`, `hidden_dims`
- Short, clear names for counters/iterators: `n_batches`, `n_samples`, `n_before`, `n_after`

**Feature/Column Names:**
- `snake_case` for all DataFrame columns and feature names: `route_distance_stop1`, `time_of_day_sin`, `passenger_count`
- Suffixed with unit when ambiguous: `timestamp_ms`, `current_delay_sec`, `max_eta_seconds`, `precipitation_mm`
- Boolean flags use `is_` prefix: `is_rush_hour`, `is_class_change`, `is_raining`, `is_game_day`

## Code Style

**Formatting:**
- No `pyproject.toml`, `.flake8`, or `.prettierrc` detected — no enforced formatter
- 4-space indentation throughout
- Line lengths appear to stay under ~120 characters; f-strings used heavily for formatting
- Blank lines used consistently to separate logical blocks within functions

**Type Annotations:**
- Consistent use of Python type hints on function signatures throughout all well-structured modules
- `from typing import Optional, Dict, List, Any` imported in every typed module
- `from pathlib import Path` used universally instead of string paths
- Return type annotations present on most public functions: `-> dict`, `-> tuple`, `-> nn.Module`
- Modern union syntax (`list[str]`, `dict[str, int]`) used in newer files, `List[str]` in older ones

**Docstrings:**
- Google-style docstrings on all public classes and functions with `Args:` and `Returns:` sections
- Module-level docstrings on every file with purpose, usage example, and input/output description
- ASCII diagrams used in complex class docstrings (e.g., `ETAPredictor` architecture diagram in `ETA-Model/src/model.py`)

## Import Organization

**Order (consistently followed):**
1. Standard library: `json`, `sys`, `time`, `argparse`, `pathlib`, `datetime`, `typing`, `dataclasses`
2. Third-party: `numpy`, `pandas`, `torch`, `xgboost`, `fastapi`, `tqdm`
3. Local/relative: `from .config import ...`, `from model import ...`, `from build_features import ...`

**Path manipulation for local imports:**
- Scripts use `sys.path.insert(0, str(Path(__file__).resolve().parent))` when importing sibling modules
- `ETA-Model/src/` modules use relative imports: `from model import ...`, `from loss import ...`
- `ETA-Model/data_prep/` package uses package-relative imports: `from .config import ...`

**Path Aliases:**
- None (no `__init__.py`-based aliasing, no pyproject package config)
- `BASE_DIR = Path(__file__).parent.parent` pattern used in config modules

## Error Handling

**Patterns:**
- Specific exceptions raised with descriptive f-string messages: `raise ValueError(f"Unknown model type: {model_type}")`
- `raise FileNotFoundError(f"Features not found at {features_path}")` for missing files
- JSONL parsing uses narrow `except json.JSONDecodeError: continue` to skip bad lines silently
- Data validation uses `assert len(df) == n_before, f"Row explosion on merge: {n_before} -> {len(df)}"` inline
- Production inference uses broad `except Exception: pass` in optional feature extraction (e.g., `extract_weather_features` in `ETA-Model/src/features.py:319`)
- Factory functions raise `ValueError` for unknown string identifiers: `create_model`, `create_loss_function`

**Guard patterns:**
- Early return `None` or empty DataFrame for invalid/missing inputs
- `if not record['vid'] or not record['timestamp_ms']: return None` — falsy guard before appending
- Constructor validation: `if overestimate_penalty < 1.0: raise ValueError(...)` in `AsymmetricETALoss`

## Logging

**Framework:** `print()` — no `logging` module used anywhere

**Patterns:**
- Progress sections labeled with `print(f"\n[Step N/M] Doing X...")` in pipeline classes
- Section separators: `print("=" * 60)` before major blocks
- Debug output gated behind a `debug: bool` parameter passed to constructors
- f-string format for all print output: `print(f"Filtered: {n_before:,} -> {n_after:,} records")`
- Scripts print to stdout; no log files or structured logging

## Comments

**When to Comment:**
- Inline comments for non-obvious numeric constants: `# Allow for small floating point differences`
- Section dividers using `# ====...` blocks in config files and long scripts
- Algorithm explanations before complex math: loss function math written out in comment above code
- `# NOTE:` prefix for important behavioral caveats

**Module and Class Headers:**
- Every module has a docstring explaining purpose, usage example, input/output
- Every public class has a docstring with design rationale (not just "what")

## Function Design

**Size:** Functions are generally focused; large pipeline scripts (`evaluate.py` at 1217 lines, `build_differentiator_features.py` at 1128 lines) are long but logically sectioned with section-header comments

**Parameters:**
- Keyword arguments with defaults for all optional params
- `Optional[type] = None` pattern for truly optional args (often resolved to defaults inside function body)
- Factory pattern used for complex objects: `create_model(...)`, `create_loss_function(...)`

**Return Values:**
- Dictionaries for metric results: `{'overall_mae': float, 'per_stop_mae': list, ...}`
- Tuples for multi-value returns: `tuple[float, float]`, `tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]`
- `Path` objects returned for file locations

## Module Design

**Exports:** No explicit `__all__` declarations; all public names are importable

**Barrel Files:** `ETA-Model/data_prep/__init__.py` and `ETA-Model/src/__init__.py` are empty — no barrel re-exports

**Factory Functions:**
- `create_model(model_type='standard', ...)` in `ETA-Model/src/model.py`
- `create_loss_function(loss_type='asymmetric', ...)` in `ETA-Model/src/loss.py`
- Factory + `if/elif/else: raise ValueError` is the standard dispatch pattern

**Constants Pattern:**
- Module-level list/dict constants defined at top of file after imports
- Feature column lists stored as module constants: `CORE_FEATURES`, `FEATURE_COLS`, `CATEGORICAL_COLS`
- Used as single source of truth across train/eval scripts via import

---

*Convention analysis: 2026-03-25*
