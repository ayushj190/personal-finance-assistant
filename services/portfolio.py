from typing import Any


def calculate_drift(
    current_values: dict[str, float],
    targets: dict[str, float],
    drift_band_pct: float = 5.0,
) -> list[dict[str, Any]]:
    total_val = sum(current_values.values())
    results: list[dict[str, Any]] = []

    # All buckets present in targets or current_values
    all_buckets = sorted(set(current_values.keys()) | set(targets.keys()))

    for bucket in all_buckets:
        val = current_values.get(bucket, 0.0)
        actual_pct = (val / total_val * 100.0) if total_val > 0 else 0.0
        target_pct = targets.get(bucket, 0.0)
        diff_pp = actual_pct - target_pct

        # 5/25 rule: absolute drift > band OR relative drift > 25% of target
        is_abs_drift = abs(diff_pp) > drift_band_pct
        is_rel_drift = (abs(diff_pp) / target_pct > 0.25) if target_pct > 0 else (actual_pct > 0)
        alert = is_abs_drift or is_rel_drift

        results.append(
            {
                "bucket": bucket,
                "value_eur": val,
                "actual_pct": actual_pct,
                "target_pct": target_pct,
                "drift_pp": diff_pp,
                "alert": alert,
            }
        )
    return results


def rebalance_without_selling(
    current_values: dict[str, float],
    targets: dict[str, float],
) -> tuple[float, dict[str, float]]:
    all_buckets = sorted(set(current_values.keys()) | set(targets.keys()))
    # Filter targets > 0
    valid_targets = {b: targets.get(b, 0.0) for b in all_buckets if targets.get(b, 0.0) > 0}
    if not valid_targets:
        return 0.0, {}

    # Ratio of current value to target fraction
    total_needed = max(current_values.get(b, 0.0) / (valid_targets[b] / 100.0) for b in valid_targets)
    buys: dict[str, float] = {}
    for b in valid_targets:
        target_val = (valid_targets[b] / 100.0) * total_needed
        buys[b] = max(0.0, target_val - current_values.get(b, 0.0))

    total_new_cash = sum(buys.values())
    return total_new_cash, buys


def allocate_contribution(
    current_values: dict[str, float],
    targets: dict[str, float],
    contribution: float,
) -> dict[str, float]:
    if contribution <= 0:
        return {b: 0.0 for b in targets}

    all_buckets = sorted(set(current_values.keys()) | set(targets.keys()))
    valid_targets = {b: targets.get(b, 0.0) for b in all_buckets if targets.get(b, 0.0) > 0}
    if not valid_targets:
        return {}

    # Water-filling allocation iteratively
    vals = {b: float(current_values.get(b, 0.0)) for b in valid_targets}
    allocations = {b: 0.0 for b in valid_targets}
    remaining = float(contribution)
    step = min(1.0, remaining / 100.0) if remaining > 10 else 0.1

    while remaining > 1e-4:
        total = sum(vals.values())
        # Find bucket with lowest ratio of actual to target
        ratios = {b: (vals[b] / total) / (valid_targets[b] / 100.0) if total > 0 else 0.0 for b in valid_targets}
        min_bucket = min(ratios, key=ratios.get)  # type: ignore

        cur_step = min(step, remaining)
        vals[min_bucket] += cur_step
        allocations[min_bucket] += cur_step
        remaining -= cur_step

    return allocations


def full_rebalance(
    current_values: dict[str, float],
    targets: dict[str, float],
) -> dict[str, float]:
    total_val = sum(current_values.values())
    all_buckets = sorted(set(current_values.keys()) | set(targets.keys()))
    deltas: dict[str, float] = {}

    for b in all_buckets:
        target_pct = targets.get(b, 0.0)
        target_val = (target_pct / 100.0) * total_val
        cur_val = current_values.get(b, 0.0)
        deltas[b] = target_val - cur_val

    return deltas
