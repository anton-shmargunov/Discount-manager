"""
End-to-end smoke test using the real input files from inputs/.
Run with:  python tests/test_e2e.py
"""

import sys
import math
from collections import Counter

sys.path.insert(0, ".")

import pandas as pd

from core.analytics.basket_analysis import (
    run_basket_analysis,
    run_tracking_report_analysis,
    run_tracking_product_bs_report_analysis,
    apply_kmeans,
    apply_octants,
    compute_sumup_series,
)
from core.modeling.regression import fit_plane, fit_line, paired_values_skipping_zero_x, values_skipping_last
from core.analytics.cost_correction import (
    COST_CORRECTION_FROM_LAST_POINT,
    COST_CORRECTION_FROM_REGRESSION,
    compute_corrections_for_baskets,
    compute_cost_margin_correction,
    enrich_sumup_with_corrected_totals,
    fit_bulk_cost_price,
    hybrid_margin_map,
    last_fitted_index,
    skipped_tail_indices,
)
from core.optimization.price_optimization import evaluate_week_margin_model
from core.statistics.metrics import monthly_reserve, ratio_series, safe_ratio
from core.transforms.data_prep import (
    tracking_report_to_metric_frames,
    tracking_product_bs_report_to_frame_sets,
)
from visualizations.sumup_charts import build_metric_progress


def main():
    print("Loading input files...")
    df_sold  = pd.read_csv("inputs/SoldQty_tot.csv")
    df_price = pd.read_csv("inputs/AvgSalePrice_tot.csv")
    df_m     = pd.read_csv("inputs/M_tot.csv")
    df_stock = pd.read_csv("inputs/Stock_tot.csv")

    # ── Build ─────────────────────────────────────────────────────────────
    print("Running basket analysis...")
    result = run_basket_analysis(df_sold, df_price, df_m, df_stock, min_price=0.001)
    print(f"  Baskets : {result.basket_count}")
    print(f"  Weeks   : {result.week_count}")
    assert result.basket_count > 0,  "No baskets produced"
    assert result.week_count   > 0,  "No weeks produced"

    print("\nFirst 5 basket results:")
    for b in result.basket_results[:5]:
        sp = "N/A" if math.isnan(b.corr_SP) else f"{b.corr_SP:.3f}"
        ms = "N/A" if math.isnan(b.corr_MS) else f"{b.corr_MS:.3f}"
        print(f"  basket={b.basket:>6}  corr_SP={sp}  corr_MS={ms}"
              f"  sold={b.total_sold:>8.0f}  group={b.group}")

    # ── K-Means ───────────────────────────────────────────────────────────
    print("\nRunning K-Means (k=3)...")
    r_km = apply_kmeans(result, k=3)
    grp  = Counter(b.group for b in r_km.basket_results)
    print("  Group distribution:", dict(sorted(grp.items())))
    assert set(grp.keys()) <= {1, 2, 3}, f"Unexpected groups: {grp}"

    # ── Octants ───────────────────────────────────────────────────────────
    print("\nRunning Octants...")
    r_oct = apply_octants(result)
    oct   = Counter(b.group for b in r_oct.basket_results)
    print("  Octant distribution:", dict(sorted(oct.items())))
    assert all(1 <= g <= 8 for g in oct.keys()), f"Unexpected octants: {oct}"

    # ── Cluster Summary ───────────────────────────────────────────────────
    print("\nK-Means cluster summaries:")
    for s in r_km.get_cluster_summary():
        if s.get("count", 0) == 0:
            continue
        print(f"  Group {s['group']}: {s['count']} baskets  "
              f"W.Price={s['weighted_price']:.2f}  "
              f"avg_corr_SP={s['avg_corr_SP']:.3f}")

    # ── Sum-Up ────────────────────────────────────────────────────────────
    print("\nSum-Up weekly rows:")
    su_rows = compute_sumup_series(result.weekly_totals, result.all_weeks)
    assert len(su_rows) == result.week_count
    for row in su_rows:
        wk = row["week"]
        sp = "N/A" if math.isnan(row["corr_SP"]) else f"{row['corr_SP']:.3f}"
        print(f"  {wk}  sold={row['total_sold']:>8.0f}  m={row['total_m']:>10.2f}  corr_SP={sp}")

    first_su = su_rows[0]
    expected_mr = monthly_reserve(first_su["total_stock"], first_su["total_sold"])
    assert abs(first_su["total_monthly_reserve"] - expected_mr) < 1e-9, (
        first_su["total_monthly_reserve"], expected_mr
    )
    assert abs(monthly_reserve(30.0, 7.0) - 1.0) < 1e-9
    assert math.isnan(safe_ratio(10.0, 0.0))
    assert abs(safe_ratio(10.0, 2.0) - 5.0) < 1e-9
    assert abs(ratio_series([10.0], [5.0])[0] - 2.0) < 1e-9

    from core.analytics.week_basket_tables import (
        WeekDiscountViewSettings,
        apply_week_discount_filters,
        build_week_discount_column_meta,
        build_week_discount_columns,
        compute_basket_week_detail_rows,
        compute_basket_week_discount_rows,
        expand_week_discount_export_rows,
        normalize_week_discount_export_rows,
        ratio_change,
        select_visible_week_discount_columns,
        week_discount_column_background,
        week_discount_column_group,
        week_discount_filter_columns,
        format_week_discount_value,
        parse_week_discount_filter_value,
    )
    show_week = str(first_su["week"])
    detail_rows = compute_basket_week_detail_rows(
        result.basket_data, result.weekly_totals, show_week,
    )
    assert len(detail_rows) == result.weekly_totals[show_week].valid_baskets
    assert "Corr S/P" not in detail_rows[0]
    assert "Basket" in detail_rows[0]
    assert "Total Margin Corrected" in detail_rows[0]
    assert "Cost Corrected" in detail_rows[0]
    assert abs(detail_rows[0]["Total Margin Corrected"] - detail_rows[0]["Total Margin"]) < 1e-9
    discount_rows, discount_cols = compute_basket_week_discount_rows(
        result.basket_data, result.weekly_totals, result.all_weeks, show_week,
    )
    assert len(discount_rows) == len(detail_rows)
    assert discount_cols[0] == "Basket"
    assert "dSt_QW" in discount_cols
    assert "New Discount" in discount_cols
    assert "New Prom" in discount_cols
    assert "dDiscount" in discount_cols
    assert "dProm" in discount_cols
    assert "dDisc_QW" not in discount_cols
    assert "dProm_QW" not in discount_cols
    assert "dPrice_QW" in discount_cols
    assert "dRes_QW" in discount_cols
    assert week_discount_column_group("New Discount") == ("discount", False)
    assert week_discount_column_group("New Prom") == ("prom", False)
    assert week_discount_column_group("dRes_QW") == ("reserve", True)
    assert week_discount_column_group("dSt_QW") == ("stock", True)
    assert week_discount_column_background("New Discount") == "#fecdd3"
    assert week_discount_column_background("dDiscount") == "#fda4af"
    wd_meta = build_week_discount_column_meta(
        result.weekly_totals, result.all_weeks, show_week,
    )
    wd_filters = week_discount_filter_columns(wd_meta)
    assert wd_filters["prom_current"] != "New Prom"
    assert wd_filters["discount_current"] != "New Discount"
    assert wd_filters["prom_current"].startswith("Prom[")
    assert wd_filters["discount_current"].startswith("Discount[")
    assert week_discount_column_background(wd_filters["stock_current"]) == "#fce7f3"
    assert wd_filters["stock_current"] in discount_cols
    visible_all = select_visible_week_discount_columns(
        discount_cols, wd_meta, WeekDiscountViewSettings(),
    )
    assert "dRes_QW" not in visible_all
    assert "New Discount" not in visible_all
    assert "New Prom" not in visible_all
    visible_with_reserve = select_visible_week_discount_columns(
        discount_cols,
        wd_meta,
        WeekDiscountViewSettings(show_reserve=True),
    )
    assert "dRes_QW" in visible_with_reserve
    visible_with_discount_prom = select_visible_week_discount_columns(
        discount_cols,
        wd_meta,
        WeekDiscountViewSettings(show_discount=True, show_prom=True),
    )
    assert "New Discount" in visible_with_discount_prom
    assert "New Prom" in visible_with_discount_prom
    visible_no_w1 = select_visible_week_discount_columns(
        discount_cols,
        wd_meta,
        WeekDiscountViewSettings(show_w1=False),
    )
    assert all(
        wd_meta[col].get("offset") != -1 or wd_meta[col].get("is_delta")
        for col in visible_no_w1
        if col != "Basket"
    )
    filtered = apply_week_discount_filters(
        discount_rows,
        {wd_filters["dSt_QW"]: (0.0, None)},
    )
    assert len(filtered) <= len(discount_rows)
    assert format_week_discount_value("dSt_QW", 0.105) == "10.50%"
    assert format_week_discount_value(wd_filters["stock_current"], 1234.6) == "1235"
    assert format_week_discount_value(wd_filters["margin_current"], 1234.567) == "$1,234.57"
    assert parse_week_discount_filter_value("dSt_QW", -10.5) == -0.105
    assert parse_week_discount_filter_value("Stock", 12.7) == 13.0
    assert parse_week_discount_filter_value("Monthly Reserve", 1.25) == 1.25
    assert format_week_discount_value("dRes_QW", 0.05) == "5.00%"
    assert wd_filters["reserve_current"] in discount_cols
    assert abs(ratio_change(110.0, 100.0) - 0.1) < 1e-9

    first_week = str(result.all_weeks[0])
    early_discount_cols = build_week_discount_columns(
        result.weekly_totals, result.all_weeks, first_week,
    )
    assert len(early_discount_cols) == len(set(early_discount_cols))
    missing_offset_cols = [
        col for col in early_discount_cols if "|W-" in col or "|W0" in col
    ]
    assert len(missing_offset_cols) >= 3

    from core.analytics.discount_strategy import (
        DiscountStrategySettings,
        StrategyTable,
        apply_manual_overrides_to_rows,
        build_working_week_discount_rows,
        compute_new_discount_value,
        default_margin_categories,
        default_moderate_bins,
        load_discount_strategy_settings,
        load_strategies_v1,
        lookup_mtost_d_discount,
        lookup_strategy_d_discount,
        mtost_strategy_applies,
        week_discount_group_column_at_offset,
    )
    margin_defaults = default_margin_categories()
    assert len(margin_defaults) == 4
    assert margin_defaults[0].strategy == "Conservative"
    assert margin_defaults[1].strategy == "Conservative"
    assert margin_defaults[2].strategy == "Moderate"
    moderate_table = StrategyTable("Moderate", default_moderate_bins())
    assert lookup_strategy_d_discount(-0.55, moderate_table) == 0.05
    assert lookup_strategy_d_discount(-0.40, moderate_table) == 0.04
    from core.analytics.week_basket_tables import (
        compute_week_discount_summary,
        compute_week_discount_weighted_comparison,
        compute_week_discount_weighted_comparisons,
        discount_prom_weight_column_labels,
        weighted_discount_prom_series,
        enrich_week_discount_delta_columns,
        weighted_discount_prom_series_all,
    )

    enriched = enrich_week_discount_delta_columns(discount_rows, wd_filters)
    assert "dDiscount" in enriched[0]
    assert len(enriched[0]) >= len(discount_rows[0])

    manual_overrides = {
        str(discount_rows[0]["Basket"]): {
            "New Discount": 0.05,
            "New Prom": 0.02,
        },
    }
    manual_rows = apply_manual_overrides_to_rows(discount_rows, manual_overrides)
    assert manual_rows[0]["New Discount"] == 0.05
    assert manual_rows[0]["New Prom"] == 0.02
    manual_enriched = enrich_week_discount_delta_columns(manual_rows, wd_filters)
    assert manual_enriched[0]["New Discount"] == 0.05
    assert manual_enriched[0]["New Prom"] == 0.02
    sample_row = dict(enriched[0])
    sample_row["New Prom"] = 0.07
    sample_row[wd_filters["prom_current"]] = 0.02
    prom_delta_row = enrich_week_discount_delta_columns([sample_row], wd_filters)[0]
    assert abs(prom_delta_row["dProm"] - 0.05) < 1e-6
    missing_current_row = {
        "Basket": "9999",
        "New Prom": 0.02,
        wd_filters["prom_current"]: float("nan"),
    }
    missing_prom_delta = enrich_week_discount_delta_columns(
        [missing_current_row], wd_filters,
    )[0]
    assert abs(missing_prom_delta["dProm"] - 0.02) < 1e-6
    missing_new_prom_row = {
        "Basket": "9998",
        "New Prom": float("nan"),
        wd_filters["prom_current"]: 0.02,
    }
    missing_new_prom_delta = enrich_week_discount_delta_columns(
        [missing_new_prom_row], wd_filters,
    )[0]
    assert abs(missing_new_prom_delta["dProm"] - (-0.02)) < 1e-6
    missing_new_discount_row = {
        "Basket": "9997",
        "New Discount": float("nan"),
        wd_filters["discount_current"]: -0.10,
    }
    missing_new_discount_delta = enrich_week_discount_delta_columns(
        [missing_new_discount_row], wd_filters,
    )[0]
    assert abs(missing_new_discount_delta["dDiscount"] - 0.10) < 1e-6
    pipeline_base = [dict(discount_rows[0])]
    pipeline_base[0][wd_filters["prom_current"]] = 0.02
    pipeline_row = build_working_week_discount_rows(
        pipeline_base,
        wd_filters,
        manual_overrides={
            str(discount_rows[0]["Basket"]): {"New Prom": 0.07},
        },
    )[0]
    assert pipeline_row["New Prom"] == 0.07
    assert abs(pipeline_row["dProm"] - 0.05) < 1e-6

    from core.analytics.prom_strategy import (
        PromStrategySettings,
        apply_generated_proms_to_rows,
        generate_week_prom_values,
    )

    prom_settings = PromStrategySettings(mode="Set previous prom")
    prom_generated = generate_week_prom_values(discount_rows, wd_filters, prom_settings)
    assert len(prom_generated) == len(discount_rows)
    sample_basket = str(discount_rows[0]["Basket"])
    prom_prom_rows = apply_generated_proms_to_rows(discount_rows, prom_generated)
    gen_prom = prom_generated[sample_basket]
    applied_prom = prom_prom_rows[0]["New Prom"]
    assert (
        gen_prom == applied_prom
        or (isinstance(gen_prom, float) and isinstance(applied_prom, float)
            and math.isnan(gen_prom) and math.isnan(applied_prom))
    )

    wd_summary = compute_week_discount_summary(enriched, wd_filters)
    assert "max_dProm" in wd_summary
    wd_compare = compute_week_discount_weighted_comparison(enriched, wd_meta, wd_filters)
    assert set(wd_compare) == {"current_minus_1w", "current", "new"}
    assert "W_Discount" in wd_compare["new"]
    assert "count_Prom" in wd_compare["current"]
    stock_compare = compute_week_discount_weighted_comparison(
        enriched, wd_meta, wd_filters, weight_metric="stock",
    )
    sold_compare = compute_week_discount_weighted_comparison(
        enriched, wd_meta, wd_filters, weight_metric="sold",
    )
    count_compare = compute_week_discount_weighted_comparison(
        enriched, wd_meta, wd_filters, weight_metric="count_product",
    )
    assert discount_prom_weight_column_labels("stock") == ("W.S. Discount", "W.S. Prom")
    assert discount_prom_weight_column_labels("count_product") == (
        "W.C. Discount",
        "W.C. Prom",
    )
    assert discount_prom_weight_column_labels("sold") == (
        "W.Sold Discount",
        "W.Sold Prom",
    )
    assert stock_compare["current"]["W_Discount"] == wd_compare["current"]["W_Discount"]
    assert math.isfinite(stock_compare["current"]["W_Discount"])
    assert math.isfinite(sold_compare["current"]["W_Discount"])
    synthetic_rows = [
        {
            "New Discount": -0.10,
            "New Prom": 0.02,
            wd_filters["stock_current"]: 100.0,
            wd_filters["count_product_current"]: 1.0,
            wd_filters["sold_current"]: 80.0,
        },
        {
            "New Discount": -0.50,
            "New Prom": 0.10,
            wd_filters["stock_current"]: 100.0,
            wd_filters["count_product_current"]: 9.0,
            wd_filters["sold_current"]: 20.0,
        },
    ]
    synth_all = compute_week_discount_weighted_comparisons(
        synthetic_rows, wd_meta, wd_filters,
    )
    assert set(synth_all) == {"stock", "count_product", "sold"}
    synth_stock = synth_all["stock"]
    synth_sold = synth_all["sold"]
    synth_count = synth_all["count_product"]
    assert synth_stock == compute_week_discount_weighted_comparison(
        synthetic_rows, wd_meta, wd_filters, weight_metric="stock",
    )
    assert abs(synth_stock["new"]["W_Discount"] - (-0.30)) < 1e-9
    assert abs(synth_stock["new"]["W_Prom"] - 0.06) < 1e-9
    assert abs(synth_sold["new"]["W_Discount"] - (-0.18)) < 1e-9
    assert abs(synth_sold["new"]["W_Prom"] - 0.036) < 1e-9
    assert abs(synth_count["new"]["W_Discount"] - (-0.46)) < 1e-9
    assert abs(synth_count["new"]["W_Prom"] - 0.092) < 1e-9
    assert synth_count["new"]["count_Prom"] == 2

    from core.models import BasketTimeSeries
    ts_a = BasketTimeSeries(
        basket="A",
        weeks=["2026-20"],
        quadweeks=["N/A"],
        sold=[80.0],
        price=[10.0],
        m=[1.0],
        stock=[100.0],
        cost=[9.0],
        count_product=[1.0],
        discount=[-0.10],
        prom=[0.02],
    )
    ts_b = BasketTimeSeries(
        basket="B",
        weeks=["2026-20"],
        quadweeks=["N/A"],
        sold=[20.0],
        price=[10.0],
        m=[1.0],
        stock=[100.0],
        cost=[9.0],
        count_product=[9.0],
        discount=[-0.50],
        prom=[0.10],
    )
    series_all = weighted_discount_prom_series_all(
        {"A": ts_a, "B": ts_b}, ["2026-20"],
    )
    assert set(series_all) == {"stock", "count_product", "sold"}
    series_stock_d, series_stock_p = series_all["stock"]
    series_sold_d, series_sold_p = series_all["sold"]
    assert series_all["stock"] == weighted_discount_prom_series(
        {"A": ts_a, "B": ts_b}, ["2026-20"], weight_metric="stock",
    )
    assert abs(series_stock_d[0] - (-0.30)) < 1e-9
    assert abs(series_stock_p[0] - 0.06) < 1e-9
    assert abs(series_sold_d[0] - (-0.18)) < 1e-9
    assert abs(series_sold_p[0] - 0.036) < 1e-9
    count_product_cols = [
        col for col in discount_cols if col.startswith("Count Product[")
    ]
    assert len(count_product_cols) == 4
    visible_count_product = select_visible_week_discount_columns(
        discount_cols,
        wd_meta,
        WeekDiscountViewSettings(show_count_product=True),
    )
    assert any(col.startswith("Count Product[") for col in visible_count_product)
    assert wd_filters["count_product_current"] in discount_cols

    from configs.settings import FULL_BASKET_LIST_PATH, FULL_BASKET_LIST_SIZE
    from core.transforms.data_prep import parse_full_basket_list
    from ui.product_bs_scope import (
        default_product_bs_scope_state,
        get_product_bs_scope,
        product_bs_scope_key,
        scoped_widget_key,
    )

    assert product_bs_scope_key(
        "TrackingBaskets_v2 - product_BS. on date of sale",
        "In",
    ) != product_bs_scope_key(
        "TrackingBaskets_v2 - product_BS. on date of sale",
        "Out",
    )
    class _FakeSS(dict):
        pass

    fake_ss = _FakeSS()
    in_scope = get_product_bs_scope(fake_ss, product_bs_scope_key("pbs::mode", "In"))
    out_scope = get_product_bs_scope(fake_ss, product_bs_scope_key("pbs::mode", "Out"))
    in_scope["analysis"] = object()
    assert out_scope["analysis"] is None
    assert scoped_widget_key("a", "b") == "a::b"
    assert "analysis" in default_product_bs_scope_state()

    full_baskets = parse_full_basket_list(pd.read_csv(FULL_BASKET_LIST_PATH))
    assert len(full_baskets) == FULL_BASKET_LIST_SIZE, len(full_baskets)
    assert full_baskets[0] == "1111"
    assert full_baskets[-1] == "5555"
    expanded = expand_week_discount_export_rows(
        discount_rows,
        discount_cols,
        full_baskets,
    )
    assert len(expanded) == FULL_BASKET_LIST_SIZE
    assert expanded[0]["Basket"] == "1111"
    assert expanded[-1]["Basket"] == "5555"
    present_basket = str(discount_rows[0]["Basket"])
    present_row = next(r for r in expanded if r["Basket"] == present_basket)
    orig_nd = discount_rows[0]["New Discount"]
    exp_nd = present_row["New Discount"]
    assert (
        orig_nd == exp_nd
        or (isinstance(orig_nd, float) and isinstance(exp_nd, float) and math.isnan(orig_nd) and math.isnan(exp_nd))
    )
    if present_basket != "1121":
        missing_row = next(r for r in expanded if r["Basket"] == "1121")
        assert math.isnan(missing_row["New Discount"])
        assert math.isnan(missing_row["New Prom"])
    in_stock_baskets = {str(r["Basket"]) for r in discount_rows}
    export_ready = normalize_week_discount_export_rows(
        expanded,
        discount_cols,
        fill_baskets=in_stock_baskets,
    )
    missing_export = next(r for r in export_ready if r["Basket"] == "1121")
    assert math.isnan(missing_export["New Discount"])
    assert math.isnan(missing_export["New Prom"])
    in_stock_export = next(r for r in export_ready if r["Basket"] == present_basket)
    if math.isnan(discount_rows[0]["New Prom"]):
        assert in_stock_export["New Prom"] == 0.0
    if math.isnan(discount_rows[0]["New Discount"]):
        assert in_stock_export["New Discount"] == 0.0

    from core.models import WeeklyTotal
    from core.transforms.data_prep import (
        advance_discount_hist_week_metadata,
        build_discount_hist_export_rows,
    )

    wt_mid = WeeklyTotal(
        week="2025-34",
        sum_sold=1.0,
        sum_m=1.0,
        sum_sold_price=1.0,
        sum_stock=1.0,
        valid_baskets=1,
        quadweek="8",
        week_in_quad=3,
    )
    meta_mid = advance_discount_hist_week_metadata({"2025-34": wt_mid}, "2025-34")
    assert meta_mid["year_week"] == "2025-35"
    assert meta_mid["week from y_w (1_52)"] == 35
    assert meta_mid["week in quad (1_4)"] == 4
    assert meta_mid["quadweek"] == 8

    wt_qw_end = WeeklyTotal(
        week="2025-34",
        sum_sold=1.0,
        sum_m=1.0,
        sum_sold_price=1.0,
        sum_stock=1.0,
        valid_baskets=1,
        quadweek="8",
        week_in_quad=4,
    )
    meta_qw_end = advance_discount_hist_week_metadata({"2025-34": wt_qw_end}, "2025-34")
    assert meta_qw_end["week in quad (1_4)"] == 1
    assert meta_qw_end["quadweek"] == 9

    wt_roll = WeeklyTotal(
        week="2025-52",
        sum_sold=1.0,
        sum_m=1.0,
        sum_sold_price=1.0,
        sum_stock=1.0,
        valid_baskets=1,
        quadweek="13",
        week_in_quad=2,
    )
    meta_roll = advance_discount_hist_week_metadata({"2025-52": wt_roll}, "2025-52")
    assert meta_roll["year_week"] == "2026-1"
    assert meta_roll["week from y_w (1_52)"] == 1

    hist_rows = build_discount_hist_export_rows(
        [{
            "Basket": "2312",
            "New Discount": -0.10,
            "New Prom": 0.02,
        }],
        meta_mid,
        "Aggregated",
    )
    assert hist_rows[0]["year_week"] == "2025-35"
    assert hist_rows[0]["discount"] == "-0.1"
    assert hist_rows[0]["prom with stock"] == "0.02"
    assert hist_rows[0]["BasketDiscountInMarket"] == ""

    from core.transforms.data_prep import merge_discount_hist_export

    df_hist_source = pd.read_csv("inputs/discount_hist_EXAMPLE_SHORT.csv")
    merged_hist = merge_discount_hist_export(
        df_hist_source,
        hist_rows,
        include_all_history=True,
    )
    assert len(merged_hist) > len(hist_rows)
    assert any(
        str(r["year_week"]) == "2025-34" and str(r["basket"]) == "2312"
        for r in merged_hist
    )
    new_only = merge_discount_hist_export(
        df_hist_source,
        hist_rows,
        include_all_history=False,
    )
    assert len(new_only) == len(hist_rows)
    assert all(str(r["year_week"]) == "2025-35" for r in new_only)

    from core.transforms.data_prep import (
        combine_discount_hist_export_by_category,
        merge_discount_hist_dataframes,
    )

    # Multi-file upload aggregation: separate In / Out category files → one wide row
    df_in_only = pd.DataFrame([{
        "quadweek": 8,
        "year_week": "2025-34",
        "week from y_w (1_52)": 34,
        "week in quad (1_4)": 3,
        "basket": "2312",
        "BasketDiscountInMarket": -0.25,
        "Prom, BasketDiscountInMarket": 0.04,
    }])
    df_out_only = pd.DataFrame([{
        "quadweek": 8,
        "year_week": "2025-34",
        "week from y_w (1_52)": 34,
        "week in quad (1_4)": 3,
        "basket": "2312",
        "BasketDiscountOutOfMarket": -0.10,
        "Prom, BasketDiscountOutOfMarket": 0.02,
    }])
    aggregated_upload = merge_discount_hist_dataframes([df_in_only, df_out_only])
    assert len(aggregated_upload) == 1
    row_agg = aggregated_upload.iloc[0]
    assert str(row_agg["basket"]) == "2312"
    assert float(row_agg["BasketDiscountInMarket"]) == -0.25
    assert float(row_agg["BasketDiscountOutOfMarket"]) == -0.10
    assert float(row_agg["Prom, BasketDiscountInMarket"]) == 0.04
    assert float(row_agg["Prom, BasketDiscountOutOfMarket"]) == 0.02

    # Combined all-BS-category export merge
    in_export = build_discount_hist_export_rows(
        [{"Basket": "2312", "New Discount": -0.11, "New Prom": 0.04}],
        meta_mid,
        "In",
    )
    out_export = build_discount_hist_export_rows(
        [{"Basket": "2312", "New Discount": -0.05, "New Prom": 0.02}],
        meta_mid,
        "Out",
    )
    combined_export = combine_discount_hist_export_by_category({
        "In": in_export,
        "Out": out_export,
    })
    assert len(combined_export) == 1
    assert combined_export[0]["year_week"] == "2025-35"
    assert combined_export[0]["BasketDiscountInMarket"] == "-0.11"
    assert combined_export[0]["BasketDiscountOutOfMarket"] == "-0.05"
    assert combined_export[0]["Prom, BasketDiscountInMarket"] == "0.04"
    assert combined_export[0]["Prom, BasketDiscountOutOfMarket"] == "0.02"
    assert combined_export[0]["discount"] == ""

    settings_csv = load_discount_strategy_settings("inputs/Discount settings.csv")
    assert len(settings_csv.conservative.bins) >= 5
    csv_margin = settings_csv.margin_categories
    assert len(csv_margin) == 4
    assert csv_margin[0].strategy == "Conservative"
    assert csv_margin[1].strategy == "Conservative"
    assert csv_margin[2].strategy == "Moderate"
    assert csv_margin[3].strategy == "Moderate"
    assert csv_margin[0].lower == float("-inf") and csv_margin[0].upper == 0.0
    assert csv_margin[3].lower == 1000.0 and csv_margin[3].upper == float("inf")

    from configs.settings import STRATEGIES_V1_PATH

    settings_v1 = load_strategies_v1(STRATEGIES_V1_PATH)
    assert settings_v1.sold_zero_strategy == "Conservative"
    assert abs(settings_v1.sold_zero_balance - (-0.01)) < 1e-9
    assert settings_v1.default_strategy == "Moderate"
    v1_margin = settings_v1.margin_categories
    assert len(v1_margin) == 4
    assert v1_margin[0].strategy == "Conservative"
    assert v1_margin[2].strategy == "Moderate"
    assert len(settings_v1.moderate.bins) == 10
    assert lookup_strategy_d_discount(-0.55, settings_v1.moderate) == 0.05
    assert load_discount_strategy_settings(STRATEGIES_V1_PATH).sold_zero_strategy == "Conservative"
    assert len(settings_v1.mtost.bins) == 3
    assert lookup_mtost_d_discount(0.10, settings_v1.mtost) == -0.02
    assert lookup_mtost_d_discount(0.30, settings_v1.mtost) == 0.0
    assert lookup_mtost_d_discount(0.60, settings_v1.mtost) == 0.02
    assert abs(settings_v1.mtost_balance - 0.01) < 1e-9
    assert settings_v1.mtost_strategy_enabled is True
    assert settings_v1.margin_mode == "Margin categories"

    sample_row = dict(discount_rows[0])
    mtost_settings = DiscountStrategySettings(
        mode="Based on Strategies",
        mtost_strategy_enabled=True,
        mtost_balance=0.01,
        mtost=settings_v1.mtost,
    )
    mtost_row = dict(sample_row)
    mtost_row[wd_filters["dSt_QW"]] = 0.05
    mtost_row[wd_filters["dMtoSt_QW"]] = 0.10
    mtost_row[wd_filters["margin_current"]] = 100.0
    margin_w1_col = week_discount_group_column_at_offset(wd_meta, "margin", -1)
    mtost_row[margin_w1_col] = 50.0
    mtost_row[wd_filters["discount_current"]] = -0.05
    mtost_val = compute_new_discount_value(
        mtost_row, wd_meta, wd_filters, mtost_settings,
    )
    assert abs(mtost_val - (-0.05 + (-0.02 + 0.01))) < 1e-6

    mtost_row_neg_margin = dict(mtost_row)
    mtost_row_neg_margin[wd_filters["margin_current"]] = -1.0
    default_val = compute_new_discount_value(
        mtost_row_neg_margin, wd_meta, wd_filters, mtost_settings,
    )
    assert default_val != mtost_val

    assert mtost_strategy_applies(0.05, 100.0, 50.0, mtost_settings)
    assert not mtost_strategy_applies(-0.01, 100.0, 50.0, mtost_settings)
    assert not mtost_strategy_applies(0.05, -1.0, 50.0, mtost_settings)
    assert not mtost_strategy_applies(0.05, 100.0, -1.0, mtost_settings)

    zero_settings = DiscountStrategySettings(mode="Zero all Discounts")
    assert compute_new_discount_value(
        sample_row, wd_meta, wd_filters, zero_settings,
    ) == 0.0
    prev_settings = DiscountStrategySettings(mode="Set previous discount")
    prev_val = compute_new_discount_value(
        sample_row, wd_meta, wd_filters, prev_settings,
    )
    assert prev_val == sample_row.get(wd_filters["discount_current"], 0.0) or prev_val == 0.0

    discount_current_col = wd_filters["discount_current"]
    missing_default_settings = DiscountStrategySettings(
        mode="Set previous discount",
        missing_discount_default=-0.05,
    )
    row_missing_discount = dict(sample_row)
    row_missing_discount[discount_current_col] = float("nan")
    assert compute_new_discount_value(
        row_missing_discount, wd_meta, wd_filters, missing_default_settings,
    ) == -0.05
    row_present_discount = dict(sample_row)
    row_present_discount[discount_current_col] = -0.10
    assert compute_new_discount_value(
        row_present_discount, wd_meta, wd_filters, missing_default_settings,
    ) == -0.10

    # ── Modeling on first basket ──────────────────────────────────────────
    ts = list(result.basket_data.values())[0]
    print(f"\nModeling basket '{ts.basket}' ({ts.n_weeks} weeks):")

    pf = fit_plane(ts.price, ts.stock, ts.sold, method="mlr")
    lf = fit_line(ts.price, ts.cost)
    skipped_price = values_skipping_last(ts.price, 4)
    skipped_cost = values_skipping_last(ts.cost, 4)
    assert len(skipped_price) == max(0, ts.n_weeks - 4)
    assert len(skipped_cost) == len(skipped_price)
    lf_skip = fit_line(skipped_price, skipped_cost)
    assert values_skipping_last(ts.price, 0) == list(ts.price)
    assert values_skipping_last(ts.price, ts.n_weeks) == []
    assert values_skipping_last(ts.price, ts.n_weeks + 3) == []
    keep_x, keep_y = paired_values_skipping_zero_x([0.0, 10.0, 0, 12.0], [1.0, 2.0, 3.0, 4.0], True)
    assert keep_x == [10.0, 12.0]
    assert keep_y == [2.0, 4.0]
    all_x, all_y = paired_values_skipping_zero_x([0.0, 10.0], [1.0, 2.0], False)
    assert all_x == [0.0, 10.0] and all_y == [1.0, 2.0]
    if ts.n_weeks >= 6:
        assert lf_skip is not None
        assert math.isfinite(lf_skip.z0)
        assert math.isfinite(lf_skip.a)
        assert math.isfinite(lf_skip.rmse)
        assert skipped_tail_indices(ts.n_weeks, 4) == list(range(ts.n_weeks - 4, ts.n_weeks))
        assert last_fitted_index([1.0, 0.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0], 4, True) == 4
        corr_a = compute_cost_margin_correction(
            ts.price, ts.cost, ts.sold, ts.m, lf_skip,
            4, True, COST_CORRECTION_FROM_REGRESSION, 0.0, None,
        )
        if lf_skip.a >= 0:
            assert corr_a.applied
            tail = ts.n_weeks - 1
            expected_cost = lf_skip.z0 + lf_skip.a * ts.price[tail]
            assert abs(corr_a.cost_corrected[tail] - expected_cost) < 1e-9
            assert math.isnan(corr_a.cost_corrected[0])
            expected_m = ts.m[tail] + ts.sold[tail] * (ts.cost[tail] - expected_cost)
            assert abs(corr_a.margin_hybrid[tail] - expected_m) < 1e-6
            assert corr_a.margin_hybrid[0] == ts.m[0]
            corr_b = compute_cost_margin_correction(
                ts.price, ts.cost, ts.sold, ts.m, lf_skip,
                4, True, COST_CORRECTION_FROM_LAST_POINT, 0.0, None,
            )
            assert corr_b.applied
            anchor = last_fitted_index(ts.price, 4, True)
            assert anchor is not None
            expected_b = ts.cost[anchor] - lf_skip.a * ts.price[anchor]
            assert abs(corr_b.intercept - expected_b) < 1e-9
            assert abs((lf_skip.z0 / (1.0 - lf_skip.a)) - lf_skip.pl) < 1e-6 or math.isnan(lf_skip.pl)
            blocked = compute_cost_margin_correction(
                ts.price, ts.cost, ts.sold, ts.m, lf_skip,
                4, True, COST_CORRECTION_FROM_REGRESSION, 1e9, None,
            )
            assert not blocked.applied
        else:
            blocked_neg = compute_cost_margin_correction(
                ts.price, ts.cost, ts.sold, ts.m, lf_skip,
                4, True, COST_CORRECTION_FROM_REGRESSION, 0.0, None,
            )
            assert not blocked_neg.applied

    weeks = ["2024-01", "2024-02", "2024-03", "2024-04"]
    orig = [10.0, 10.0, 10.0, 10.0]
    overlay = [float("nan"), float("nan"), 20.0, 20.0]
    qw = ["1", "1", "1", "1"]
    fig = build_metric_progress(
        weeks, orig,
        title="Cost per Sold vs Week",
        y_title="Cost per Sold",
        marker_color="rgba(16,185,129,0.75)",
        line_color="rgb(5,150,105)",
        show_qw_average=True,
        quadweeks=qw,
        overlay_values=overlay,
        overlay_name="Cost Corrected",
    )
    original_qw = [
        t for t in fig.data
        if t.name is None and getattr(t.line, "dash", None) == "dash"
    ]
    corrected_qw = [t for t in fig.data if t.name == "Corrected Average QW"]
    assert original_qw, "Original QW average should remain"
    assert abs(float(original_qw[0].y[0]) - 10.0) < 1e-9
    assert corrected_qw, "Corrected Average QW should be drawn alongside original"
    assert abs(float(corrected_qw[0].y[0]) - 15.0) < 1e-9
    assert getattr(corrected_qw[0].line, "dash", None) == "dot"

    bulk_fits = fit_bulk_cost_price(result.basket_data, 4, True)
    assert bulk_fits, "Bulk Cost x Price fit should produce at least one line"
    bulk_corrections = compute_corrections_for_baskets(
        result.basket_data,
        bulk_fits,
        4,
        True,
        COST_CORRECTION_FROM_LAST_POINT,
        None,
        None,
    )
    assert any(corr.applied for corr in bulk_corrections.values())
    su_corrected = enrich_sumup_with_corrected_totals(
        su_rows,
        result.weekly_totals,
        result.basket_data,
        bulk_corrections,
    )
    last_su = su_corrected[-1]
    assert "total_m_corrected" in last_su
    assert "total_cost_corrected" in last_su
    if last_su["total_sold"] > 0:
        expected_cost_corr = (
            (last_su["total_revenue"] - last_su["total_m_corrected"])
            / last_su["total_sold"]
        )
        assert abs(last_su["total_cost_corrected"] - expected_cost_corr) < 1e-6
    assert abs(last_su["total_m_corrected"] - last_su["total_m"]) > 1e-6

    hybrid_margins = hybrid_margin_map(result.basket_data, bulk_corrections)
    last_week = str(result.all_weeks[-1])
    detail_corr = compute_basket_week_detail_rows(
        result.basket_data,
        result.weekly_totals,
        last_week,
        margin_by_basket=hybrid_margins,
    )
    assert detail_corr
    assert any(
        abs(row["Total Margin Corrected"] - row["Total Margin"]) > 1e-6
        for row in detail_corr
    )
    wd_orig, _ = compute_basket_week_discount_rows(
        result.basket_data, result.weekly_totals, result.all_weeks, last_week,
    )
    wd_corr, _ = compute_basket_week_discount_rows(
        result.basket_data,
        result.weekly_totals,
        result.all_weeks,
        last_week,
        margin_by_basket=hybrid_margins,
    )
    assert wd_orig and wd_corr
    orig_by_basket = {row["Basket"]: row for row in wd_orig}
    changed = False
    for row in wd_corr:
        orig_row = orig_by_basket[row["Basket"]]
        if abs(float(row["dM_QW"]) - float(orig_row["dM_QW"])) > 1e-6 if (
            not math.isnan(float(row["dM_QW"]))
            and not math.isnan(float(orig_row["dM_QW"]))
        ) else False:
            changed = True
            break
        margin_cols = [c for c in row if c.startswith("Margin[")]
        if any(
            abs(float(row[c]) - float(orig_row[c])) > 1e-6
            for c in margin_cols
            if not math.isnan(float(row[c])) and not math.isnan(float(orig_row[c]))
        ):
            changed = True
            break
    assert changed, "Margin Corrected should change Week Discount Margin/dM_QW for at least one basket"

    if pf:
        print(f"  Sold plane  z0={pf.z0:.6f}  a={pf.a:.6f}  b={pf.b:.6f}  adjR2={pf.adj_r2:.4f}")
    else:
        print("  Sold plane: not enough data")

    if lf:
        print(f"  Cost line   z0={lf.z0:.6f}  a={lf.a:.6f}  Pl={lf.pl:.6f}  R2={lf.r2:.4f}")
    else:
        print("  Cost line: not enough data")

    if pf and lf:
        mres = evaluate_week_margin_model(
            ts.weeks[0], ts.price[0], ts.stock[0], ts.m[0], pf, lf
        )
        print(f"  Margin model  m_actual={mres.m_actual:.2f}  m_model={mres.m_model:.2f}"
              f"  err%={mres.m_error_pct:.2f}%  price_max={mres.price_max:.2f}")

    # ── dStock metrics ────────────────────────────────────────────────────
    print("\nStock trend metrics (first 5 baskets):")
    for b in result.basket_results[:5]:
        w = "N/A" if math.isnan(b.av_dstock_w_qw) else f"{b.av_dstock_w_qw:.3f}"
        bv = "N/A" if math.isnan(b.av_dstock_b_qw) else f"{b.av_dstock_b_qw:.3f}"
        print(f"  basket={b.basket:>6}  av_dStock_w={w}  av_dStock_b={bv}")

    # ── TrackingBaskets_v2 single-file input ───────────────────────────────
    print("\nRunning TrackingBaskets_v2 report analysis...")
    df_tracking = pd.read_csv("inputs/data (40)_short_example.csv")
    tracking_result = run_tracking_report_analysis(df_tracking, min_price=0.001)
    print(f"  Baskets : {tracking_result.basket_count}")
    print(f"  Weeks   : {tracking_result.week_count}")
    assert tracking_result.basket_count > 0, "Tracking report produced no baskets"
    assert tracking_result.week_count > 0, "Tracking report produced no weeks"
    assert "1111" in tracking_result.basket_data, "Tracking report missing basket 1111"

    from core.analytics.basket_analysis import apply_discount_hist_to_basket_data
    from core.analytics.week_basket_tables import (
        build_week_discount_column_meta,
        compute_basket_week_discount_rows,
        enrich_week_discount_delta_columns,
        week_discount_filter_columns,
    )

    tracking_hist = pd.DataFrame([{
        "year_week": "2026-12",
        "basket": 1111,
        "discount": "-0.10",
        "prom with stock": "0.02",
    }])
    apply_discount_hist_to_basket_data(
        tracking_result.basket_data,
        tracking_hist,
        "Aggregated",
    )
    ts_1111 = tracking_result.basket_data["1111"]
    week_idx = ts_1111.weeks.index("2026-12")
    assert abs(ts_1111.discount[week_idx] - (-0.10)) < 1e-6
    assert abs(ts_1111.prom[week_idx] - 0.02) < 1e-6
    wd_rows, _ = compute_basket_week_discount_rows(
        tracking_result.basket_data,
        tracking_result.weekly_totals,
        tracking_result.all_weeks,
        "2026-12",
    )
    wd_meta = build_week_discount_column_meta(
        tracking_result.weekly_totals, tracking_result.all_weeks, "2026-12",
    )
    wd_filters = week_discount_filter_columns(wd_meta)
    row_1111 = next(r for r in wd_rows if str(r["Basket"]) == "1111")
    enriched_1111 = enrich_week_discount_delta_columns([row_1111], wd_filters)[0]
    assert abs(enriched_1111["New Discount"] - (-0.10)) < 1e-6
    assert abs(enriched_1111["New Prom"] - 0.02) < 1e-6
    prom_cur_col = wd_filters["prom_current"]
    expected_dprom = enriched_1111["New Prom"] - enriched_1111[prom_cur_col]
    assert abs(enriched_1111["dProm"] - expected_dprom) < 1e-6

    synthetic_tracking = pd.DataFrame({
        "quadweek": [16, 16, 16, 17, 17, 17, 17],
        "year_week": ["2026-13", "2026-14", "2026-15", "2026-16", "2026-17", "2026-18", "2026-19"],
        "basket": ["1111"] * 7,
        "StockQty_W": [10, 11, 12, 13, 14, 15, 16],
        "CountProduct_W": [2, 3, 4, 5, 6, 7, 8],
        "PurchaseQty": [0, 1, 0, 2, 0, 3, 0],
        "SoldQty": [1, 2, 3, 4, 5, 6, 7],
        "Margin": [10, 20, 30, 40, 50, 60, 70],
        "AvgSalePrice": [100, 101, 102, 103, 104, 105, 106],
    })
    df_sold_tracking, _, _, _ = tracking_report_to_metric_frames(synthetic_tracking)
    inferred_weeks = df_sold_tracking["week in quad (1_4)"].tolist()
    assert inferred_weeks == [2, 3, 4, 1, 2, 3, 4], inferred_weeks

    blank_sales_tracking = pd.DataFrame({
        "quadweek": [19],
        "year_week": ["2026-24"],
        "basket": ["1112"],
        "StockQty_W": [51.714],
        "CountProduct_W": [1],
        "PurchaseQty": [""],
        "SoldQty": [""],
        "Margin": [""],
        "AvgSalePrice": [""],
    })
    blank_sales_result = run_tracking_report_analysis(blank_sales_tracking, min_price=0)
    blank_ts = blank_sales_result.basket_data["1112"]
    assert abs(blank_ts.sold[0] - 0.0) < 0.001, blank_ts.sold[0]
    assert abs(blank_ts.price[0] - 0.0) < 0.001, blank_ts.price[0]
    assert abs(blank_ts.stock[0] - 51.714) < 0.001, blank_ts.stock[0]
    try:
        run_tracking_report_analysis(blank_sales_tracking, min_price=0.001)
        raise AssertionError("Blank-price tracking row should be filtered by min_price=0.001")
    except ValueError as exc:
        assert "No baskets passed" in str(exc)

    # ── TrackingBaskets_v2 product_BS input ────────────────────────────────
    print("\nRunning TrackingBaskets_v2 product_BS report analysis...")
    df_product_bs = pd.read_csv("inputs/data (46).26_20_1111.category_example.csv")
    product_bs_parsed = tracking_product_bs_report_to_frame_sets(df_product_bs)
    product_bs_result, product_bs_warnings = run_tracking_product_bs_report_analysis(
        df_product_bs,
        min_price=0.001,
    )
    print(f"  Baskets : {product_bs_result.basket_count}")
    print(f"  Weeks   : {product_bs_result.week_count}")
    print(f"  Warnings: {len(product_bs_warnings)}")
    assert product_bs_result.basket_count == 1, "product_BS sample should produce one basket"
    assert product_bs_result.week_count == 1, "product_BS sample should produce one week"
    assert "1111" in product_bs_result.basket_data, "product_BS report missing basket 1111"

    agg = product_bs_parsed.aggregate
    sold_1111 = float(agg.sold.loc[agg.sold["year_week"] == "2026-20", "1111"].iloc[0])
    stock_1111 = float(agg.stock.loc[agg.stock["year_week"] == "2026-20", "1111"].iloc[0])
    count_product_1111 = float(agg.count_product.loc[agg.count_product["year_week"] == "2026-20", "1111"].iloc[0])
    purchase_1111 = float(agg.purchase.loc[agg.purchase["year_week"] == "2026-20", "1111"].iloc[0])
    margin_1111 = float(agg.margin.loc[agg.margin["year_week"] == "2026-20", "1111"].iloc[0])
    price_1111 = float(agg.price.loc[agg.price["year_week"] == "2026-20", "1111"].iloc[0])
    assert abs(sold_1111 - 57.0) < 0.1, sold_1111
    assert abs(stock_1111 - 3631.286) < 0.1, stock_1111
    assert abs(count_product_1111 - 26.0) < 0.1, count_product_1111
    assert abs(purchase_1111 - 26.0) < 0.1, purchase_1111
    assert abs(margin_1111 - (-426.88)) < 0.1, margin_1111
    assert abs(price_1111 - (2222.27 / 57.0)) < 0.01, price_1111
    recap_1111 = float(agg.recap.loc[agg.recap["year_week"] == "2026-20", "1111"].iloc[0])
    assert abs(recap_1111 - 912.82) < 0.1, recap_1111
    ts_agg = product_bs_result.basket_data["1111"]
    assert abs(ts_agg.recap[0] - 912.82) < 0.1, ts_agg.recap[0]
    su_agg = compute_sumup_series(
        product_bs_result.weekly_totals, product_bs_result.all_weeks,
    )
    assert abs(su_agg[0]["total_recap"] - 912.82) < 0.1, su_agg[0]["total_recap"]

    product_bs_in_result, _ = run_tracking_product_bs_report_analysis(
        df_product_bs,
        product_bs_category="In",
        min_price=0.001,
    )
    ts_in = product_bs_in_result.basket_data["1111"]
    assert abs(ts_in.sold[0] - 16.0) < 0.1, ts_in.sold[0]
    assert abs(ts_in.stock[0] - 679.143) < 0.1, ts_in.stock[0]
    assert abs(ts_in.count_product[0] - 5.0) < 0.1, ts_in.count_product[0]
    assert abs(product_bs_in_result.basket_data["1111"].purchase[0] - 6.0) < 0.1, ts_in.purchase[0]
    assert abs(ts_in.price[0] - (762.19 / 16.0)) < 0.01, ts_in.price[0]
    assert abs(ts_in.recap[0] - 413.11) < 0.1, ts_in.recap[0]
    assert abs(ratio_series(ts_in.sold, ts_in.stock)[0] - (16.0 / 679.143)) < 1e-6

    from core.transforms.data_prep import parse_discount_hist_lookup
    from core.analytics.basket_analysis import apply_discount_hist_to_basket_data

    df_discount_hist = pd.read_csv("inputs/discount_hist_EXAMPLE_SHORT.csv")
    lookup_in, _ = parse_discount_hist_lookup(df_discount_hist, "In")
    assert lookup_in[("2312", "2025-34")][0] == -0.25
    assert lookup_in[("2312", "2025-34")][1] == 0.04
    lookup_agg, _ = parse_discount_hist_lookup(df_discount_hist, "Aggregated")
    assert math.isnan(lookup_agg[("2314", "2025-34")][0])
    hist_warnings = apply_discount_hist_to_basket_data(
        product_bs_in_result.basket_data,
        df_discount_hist,
        "In",
    )
    assert isinstance(hist_warnings, list)

    product_bs_none_row_with_in_sale = pd.DataFrame([{
        "quadweek": 18,
        "year_week": "2026-23",
        "basket": 5152,
        "product BS": "none",
        "CountProduct_W": 1,
        "StockQty_W": 63.286,
        "PurchaseQty": 0,
        "SoldQty": 1,
        "Revenue": 162.85,
        "Margin": 91.22,
        "SoldQty_In": 1,
        "SoldQty_Out": 0,
        "SoldQty_OutByCondition": 0,
        "SoldQty_OutByMinPrice": 0,
        "SoldQty_none": 0,
        "Revenue_In": 162.85,
        "Revenue_Out": 0,
        "Revenue_OutByCondition": 0,
        "Revenue_OutByMinPrice": 0,
        "Revenue_none": 0,
        "Margin_In": 91.22,
        "Margin_Out": 0,
        "Margin_OutByCondition": 0,
        "Margin_OutByMinPrice": 0,
        "Margin_none": 0,
    }])
    none_row_parsed = tracking_product_bs_report_to_frame_sets(product_bs_none_row_with_in_sale)
    none_row_in_sold = float(
        none_row_parsed.categories["In"].sold.loc[
            none_row_parsed.categories["In"].sold["year_week"] == "2026-23",
            "5152",
        ].iloc[0]
    )
    assert abs(none_row_in_sold - 1.0) < 0.1, none_row_in_sold

    product_bs_monthly_parsed = tracking_product_bs_report_to_frame_sets(
        df_product_bs,
        use_monthly_average_metrics=True,
    )
    monthly_in = product_bs_monthly_parsed.categories["In"]
    monthly_in_sold = float(
        monthly_in.sold.loc[monthly_in.sold["year_week"] == "2026-20", "1111"].iloc[0]
    )
    monthly_in_price = float(
        monthly_in.price.loc[monthly_in.price["year_week"] == "2026-20", "1111"].iloc[0]
    )
    monthly_in_margin = float(
        monthly_in.margin.loc[monthly_in.margin["year_week"] == "2026-20", "1111"].iloc[0]
    )
    assert abs(monthly_in_sold - 21.0) < 0.1, monthly_in_sold
    assert abs(monthly_in_price - (986.6 / 21.0)) < 0.01, monthly_in_price
    assert abs(monthly_in_margin - 23.52) < 0.1, monthly_in_margin

    product_bs_monthly_in_result, _ = run_tracking_product_bs_report_analysis(
        df_product_bs,
        product_bs_category="In",
        use_monthly_average_metrics=True,
        min_price=0.001,
    )
    ts_monthly_in = product_bs_monthly_in_result.basket_data["1111"]
    assert abs(ts_monthly_in.sold[0] - 21.0) < 0.1, ts_monthly_in.sold[0]
    assert abs(ts_monthly_in.price[0] - (986.6 / 21.0)) < 0.01, ts_monthly_in.price[0]

    check_product_bs_metrics = pd.DataFrame([
        {
            "quadweek": 18,
            "year_week": "2026-23",
            "basket": 5555,
            "product BS": "BasketDiscountInMarket",
            "CountProduct_W": 646,
            "StockQty_W": 868.683,
            "PurchaseQty": 393,
            "SoldQty": 202,
            "Revenue": 29417.68,
            "Margin": 15552.27,
            "SoldQty_In": 183,
            "SoldQty_Out": 14,
            "SoldQty_OutByCondition": 4,
            "SoldQty_OutByMinPrice": 0,
            "SoldQty_none": 1,
            "Revenue_In": 26658.6,
            "Revenue_Out": 2100.6,
            "Revenue_OutByCondition": 570.15,
            "Revenue_OutByMinPrice": 0,
            "Revenue_none": 88.33,
            "Margin_In": 14040.73,
            "Margin_Out": 1176.05,
            "Margin_OutByCondition": 314.15,
            "Margin_OutByMinPrice": 0,
            "Margin_none": 21.34,
        },
        {
            "quadweek": 18,
            "year_week": "2026-23",
            "basket": 5555,
            "product BS": "BasketDiscountOutOfMarket",
            "CountProduct_W": 255,
            "StockQty_W": 300.594,
            "PurchaseQty": 123,
            "SoldQty": 88,
            "Revenue": 13258.61,
            "Margin": 7179.59,
            "SoldQty_In": 5,
            "SoldQty_Out": 78,
            "SoldQty_OutByCondition": 1,
            "SoldQty_OutByMinPrice": 0,
            "SoldQty_none": 4,
            "Revenue_In": 775.95,
            "Revenue_Out": 11851.86,
            "Revenue_OutByCondition": 104.29,
            "Revenue_OutByMinPrice": 0,
            "Revenue_none": 526.51,
            "Margin_In": 443.15,
            "Margin_Out": 6435.19,
            "Margin_OutByCondition": 43.62,
            "Margin_OutByMinPrice": 0,
            "Margin_none": 257.63,
        },
        {
            "quadweek": 18,
            "year_week": "2026-23",
            "basket": 5555,
            "product BS": "BasketDiscountOutOfMarketByCondition",
            "CountProduct_W": 105,
            "StockQty_W": 122.353,
            "PurchaseQty": 40,
            "SoldQty": 46,
            "Revenue": 7248.5,
            "Margin": 4108.38,
            "SoldQty_In": 5,
            "SoldQty_Out": 0,
            "SoldQty_OutByCondition": 41,
            "SoldQty_OutByMinPrice": 0,
            "SoldQty_none": 0,
            "Revenue_In": 868.02,
            "Revenue_Out": 0,
            "Revenue_OutByCondition": 6380.48,
            "Revenue_OutByMinPrice": 0,
            "Revenue_none": 0,
            "Margin_In": 515.23,
            "Margin_Out": 0,
            "Margin_OutByCondition": 3593.15,
            "Margin_OutByMinPrice": 0,
            "Margin_none": 0,
        },
        {
            "quadweek": 18,
            "year_week": "2026-23",
            "basket": 5555,
            "product BS": "none",
            "CountProduct_W": 65,
            "StockQty_W": 68.846,
            "PurchaseQty": 65,
            "SoldQty": 17,
            "Revenue": 2450.11,
            "Margin": 1360.33,
            "SoldQty_In": 1,
            "SoldQty_Out": 0,
            "SoldQty_OutByCondition": 0,
            "SoldQty_OutByMinPrice": 0,
            "SoldQty_none": 16,
            "Revenue_In": 146.33,
            "Revenue_Out": 0,
            "Revenue_OutByCondition": 0,
            "Revenue_OutByMinPrice": 0,
            "Revenue_none": 2303.78,
            "Margin_In": 92.2,
            "Margin_Out": 0,
            "Margin_OutByCondition": 0,
            "Margin_OutByMinPrice": 0,
            "Margin_none": 1268.13,
        },
    ])

    def _assert_single_week_metrics(result, sold, revenue, stock, purchase, count_product):
        ts = result.basket_data["5555"]
        actual_revenue = ts.sold[0] * ts.price[0]
        assert abs(ts.sold[0] - sold) < 0.1, ts.sold[0]
        assert abs(actual_revenue - revenue) < 0.1, actual_revenue
        assert abs(ts.stock[0] - stock) < 0.1, ts.stock[0]
        assert abs(ts.purchase[0] - purchase) < 0.1, ts.purchase[0]
        assert abs(ts.count_product[0] - count_product) < 0.1, ts.count_product[0]

    check_on_date_in, _ = run_tracking_product_bs_report_analysis(
        check_product_bs_metrics,
        product_bs_category="In",
        min_price=0.001,
    )
    _assert_single_week_metrics(check_on_date_in, 194, 28448.9, 868.683, 393, 646)

    check_on_date_agg, _ = run_tracking_product_bs_report_analysis(
        check_product_bs_metrics,
        product_bs_category="Aggregated",
        min_price=0.001,
    )
    _assert_single_week_metrics(check_on_date_agg, 353, 52374.9, 1360.476, 621, 1071)

    check_monthly_in, _ = run_tracking_product_bs_report_analysis(
        check_product_bs_metrics,
        product_bs_category="In",
        use_monthly_average_metrics=True,
        min_price=0.001,
    )
    _assert_single_week_metrics(check_monthly_in, 202, 29417.68, 868.683, 393, 646)

    check_monthly_agg, _ = run_tracking_product_bs_report_analysis(
        check_product_bs_metrics,
        product_bs_category="Aggregated",
        use_monthly_average_metrics=True,
        min_price=0.001,
    )
    _assert_single_week_metrics(check_monthly_agg, 353, 52374.9, 1360.476, 621, 1071)

    # ── Project save / restore (.disc_proj) ─────────────────────────────────
    print("\nProject persistence (.disc_proj)...")
    from core.persistence.project_io import (
        PROJECT_EXTENSION,
        PROJECT_MAGIC,
        apply_project_payload,
        build_project_payload,
        ensure_project_filename,
        pack_project_bytes,
        unpack_project_bytes,
    )

    assert ensure_project_filename("my proj") == f"my proj{PROJECT_EXTENSION}"
    assert ensure_project_filename("x.disc_proj") == "x.disc_proj"

    class _FakeSession(dict):
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

        def __setattr__(self, name, value):
            self[name] = value

    fake = _FakeSession()
    fake.log_messages = ["Ready."]
    fake.input_mode = "TrackingBaskets_v2 - product_BS. on date of sale"
    fake.fi_k = 3
    fake.fu_tracking_report = object()  # should be skipped by type/prefix
    fake["pbs::scope::week_discount_export_w"] = True
    fake["pbs::scope::generate_discount"] = True
    fake._pbs_scopes = {
        "pbs::TrackingBaskets_v2 - product_BS. on date of sale::Aggregated": {
            "analysis": result,
            "selected_basket": "1111",
            "selected_week": result.all_weeks[-1],
            "discount_hist_df": None,
            "fit_sold": {},
            "fit_cost": {},
            "margin_model": {},
            "show_line": False,
            "show_qw_colors": False,
            "show_qw_average": False,
            "fit_sold_m": {},
            "bulk_fit_price_sold": {},
            "bulk_fit_price_stock_sold": {},
            "bulk_fit_cost_price": {},
            "fit_sumup_cost": None,
            "fit_sumup_stock_sold": None,
            "sumup_margin_model": None,
            "sumup_select_generation": 0,
            "build_message": None,
        }
    }

    payload = build_project_payload(fake)
    blob = pack_project_bytes(payload)
    assert blob.startswith(PROJECT_MAGIC)
    restored_payload = unpack_project_bytes(blob)
    assert restored_payload["format"] == "pba_disc_proj"
    assert restored_payload["ui"]["fi_k"] == 3
    assert "fu_tracking_report" not in restored_payload["ui"]
    assert "_pbs_scopes" not in restored_payload["ui"]
    assert "pbs::scope::week_discount_export_w" not in restored_payload["ui"]
    assert "pbs::scope::generate_discount" not in restored_payload["ui"]

    dest = _FakeSession()
    dest.log_messages = ["old"]
    dest["pbs::scope::manual_edit_btn"] = True
    messages = apply_project_payload(dest, restored_payload)
    assert dest.fi_k == 3
    assert dest.input_mode == fake.input_mode
    assert dest._pbs_scopes["pbs::TrackingBaskets_v2 - product_BS. on date of sale::Aggregated"]["selected_basket"] == "1111"
    assert dest._pbs_scopes["pbs::TrackingBaskets_v2 - product_BS. on date of sale::Aggregated"]["analysis"].basket_count == result.basket_count
    assert "pbs::scope::manual_edit_btn" not in dest
    assert any("restored" in line.lower() for line in messages)
    print(f"  Project bytes: {len(blob):,}")

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
