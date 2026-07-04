"""
Automated defrost period detection using pressure differential analysis.

This module detects defrost periods by analyzing the difference between
discharge and suction pressures from compressor ports. During defrost,
these pressures converge (differential drops to ~0-10 psi).
"""

import pandas as pd
from datetime import datetime, timedelta
import logging


def get_pressure_sensors_from_compressor(data_manager):
    """
    Get the discharge and suction pressure sensor names.
    Searches inline Sensor components first, then falls back to legacy Compressor SP/DP ports.

    Returns:
        tuple: (discharge_sensor, suction_sensor) or (None, None) if not found
    """
    from port_resolver import find_suction_pressure_sensor, find_discharge_pressure_sensor

    suction_sensor = find_suction_pressure_sensor(data_manager.diagram_model)
    discharge_sensor = find_discharge_pressure_sensor(data_manager.diagram_model)

    if discharge_sensor and suction_sensor:
        logging.info(f"[DEFROST_DETECT] Found pressure sensors: DP={discharge_sensor}, SP={suction_sensor}")

    if not discharge_sensor or not suction_sensor:
        logging.error(f"[DEFROST_DETECT] Pressure sensors not mapped. Place inline Sensors with 'Suction Pressure' and 'Discharge Pressure' types, or map Compressor SP/DP ports.")
        return None, None

    return discharge_sensor, suction_sensor


def detect_defrost_periods(df, discharge_col, suction_col, threshold_psi=10, min_duration_minutes=2):
    """
    Detect defrost periods based on pressure differential.

    Algorithm:
    - Defrost starts when: abs(Discharge_Pressure - Suction_Pressure) <= threshold_psi
    - Defrost ends when: differential goes above threshold_psi
    - Filter out periods shorter than min_duration_minutes to reduce noise

    Args:
        df: DataFrame with 'Timestamp' and pressure columns
        discharge_col: Column name for discharge pressure (from Compressor.DP port)
        suction_col: Column name for suction pressure (from Compressor.SP port)
        threshold_psi: Pressure differential threshold in PSI (default: 10)
        min_duration_minutes: Minimum duration to consider a valid defrost period (default: 2)

    Returns:
        List of tuples: (start_time, end_time, duration_minutes, avg_differential)
    """
    if df is None or df.empty:
        logging.warning("[DEFROST_DETECT] Empty DataFrame provided")
        return []

    if discharge_col not in df.columns or suction_col not in df.columns:
        logging.error(f"[DEFROST_DETECT] Pressure columns not found in data: {discharge_col}, {suction_col}")
        logging.error(f"[DEFROST_DETECT] Available columns: {list(df.columns)}")
        return []

    if 'Timestamp' not in df.columns:
        logging.error("[DEFROST_DETECT] No Timestamp column found")
        return []

    logging.info(f"[DEFROST_DETECT] Using columns: DP={discharge_col}, SP={suction_col}")
    logging.info(f"[DEFROST_DETECT] Threshold: {threshold_psi} psi, Min duration: {min_duration_minutes} min")

    # Calculate pressure differential
    df_work = df.copy()
    df_work['pressure_diff'] = abs(df_work[discharge_col] - df_work[suction_col])

    # Identify defrost state (differential <= threshold)
    df_work['in_defrost'] = df_work['pressure_diff'] <= threshold_psi

    # Find transitions (defrost start/end points)
    df_work['defrost_start'] = (~df_work['in_defrost'].shift(1, fill_value=False)) & df_work['in_defrost']
    df_work['defrost_end'] = df_work['in_defrost'].shift(1, fill_value=False) & (~df_work['in_defrost'])

    # Extract defrost periods
    periods = []
    start_idx = None

    for idx, row in df_work.iterrows():
        if row['defrost_start']:
            start_idx = idx
        elif row['defrost_end'] and start_idx is not None:
            # Found end of defrost period
            start_time = df_work.loc[start_idx, 'Timestamp']
            end_time = df_work.loc[idx, 'Timestamp']

            # Calculate duration
            if isinstance(start_time, str):
                start_time = pd.to_datetime(start_time)
            if isinstance(end_time, str):
                end_time = pd.to_datetime(end_time)

            duration = (end_time - start_time).total_seconds() / 60.0  # minutes

            # Calculate average differential during this period
            period_data = df_work.loc[start_idx:idx, 'pressure_diff']
            avg_diff = period_data.mean()

            # Only include if duration meets minimum threshold
            if duration >= min_duration_minutes:
                periods.append((start_time, end_time, duration, avg_diff))
                logging.info(f"[DEFROST_DETECT] Found period: {start_time} to {end_time} ({duration:.1f} min, avg diff: {avg_diff:.1f} psi)")
            else:
                logging.debug(f"[DEFROST_DETECT] Skipped short period: {duration:.1f} min")

            start_idx = None

    # Handle case where defrost extends to end of data
    if start_idx is not None and df_work.loc[df_work.index[-1], 'in_defrost']:
        start_time = df_work.loc[start_idx, 'Timestamp']
        end_time = df_work.loc[df_work.index[-1], 'Timestamp']

        if isinstance(start_time, str):
            start_time = pd.to_datetime(start_time)
        if isinstance(end_time, str):
            end_time = pd.to_datetime(end_time)

        duration = (end_time - start_time).total_seconds() / 60.0
        period_data = df_work.loc[start_idx:, 'pressure_diff']
        avg_diff = period_data.mean()

        if duration >= min_duration_minutes:
            periods.append((start_time, end_time, duration, avg_diff))
            logging.info(f"[DEFROST_DETECT] Found period (extends to end): {start_time} to {end_time} ({duration:.1f} min)")

    logging.info(f"[DEFROST_DETECT] Total periods found: {len(periods)}")

    # Log statistics
    if periods:
        total_duration = sum(p[2] for p in periods)
        avg_duration = total_duration / len(periods)
        data_duration = (df_work['Timestamp'].iloc[-1] - df_work['Timestamp'].iloc[0]).total_seconds() / 60.0
        percentage = (total_duration / data_duration * 100) if data_duration > 0 else 0

        logging.info(f"[DEFROST_DETECT] Total defrost time: {total_duration:.1f} min ({percentage:.1f}% of data)")
        logging.info(f"[DEFROST_DETECT] Average defrost duration: {avg_duration:.1f} min")

    return periods


def get_pressure_statistics(df, discharge_col, suction_col):
    """
    Get pressure statistics from the DataFrame for display in UI.

    Args:
        df: DataFrame with pressure data
        discharge_col: Column name for discharge pressure (from Compressor.DP)
        suction_col: Column name for suction pressure (from Compressor.SP)

    Returns:
        dict with statistics about pressure columns
    """
    stats = {}

    if discharge_col and suction_col and discharge_col in df.columns and suction_col in df.columns:
        stats['discharge_col'] = discharge_col
        stats['suction_col'] = suction_col
        stats['discharge_mean'] = df[discharge_col].mean()
        stats['suction_mean'] = df[suction_col].mean()
        stats['differential_mean'] = abs(df[discharge_col] - df[suction_col]).mean()
        stats['differential_min'] = abs(df[discharge_col] - df[suction_col]).min()

    return stats
