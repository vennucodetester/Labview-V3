"""
Timestamp Diagnostic Utility
Comprehensive logging and testing for timestamp conversions in range selection
"""

import pandas as pd
from datetime import datetime
import sys

class TimestampDiagnostics:
    """Utility class for diagnosing timestamp conversion issues."""
    
    def __init__(self, enable_logging=True):
        self.enable_logging = enable_logging
        self.conversion_log = []
        
    def log_conversion(self, stage, description, value, additional_info=None):
        """Log a timestamp conversion with detailed information."""
        if not self.enable_logging:
            return
            
        log_entry = {
            'stage': stage,
            'description': description,
            'value': value,
            'value_type': type(value).__name__,
            'additional_info': additional_info or {}
        }
        
        # Add type-specific information
        if isinstance(value, datetime):
            log_entry['datetime_str'] = value.strftime('%Y-%m-%d %H:%M:%S.%f')
            log_entry['timezone'] = value.tzinfo
            log_entry['timestamp_unix'] = value.timestamp()
        elif isinstance(value, pd.Timestamp):
            log_entry['pandas_str'] = str(value)
            log_entry['timezone'] = value.tz
            log_entry['timestamp_unix'] = value.timestamp() if hasattr(value, 'timestamp') else None
        elif isinstance(value, (int, float)):
            log_entry['numeric_value'] = value
            try:
                log_entry['as_datetime'] = datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S')
            except:
                log_entry['as_datetime'] = 'INVALID'
        elif isinstance(value, pd.Series):
            log_entry['dtype'] = str(value.dtype)
            log_entry['length'] = len(value)
            log_entry['first_value'] = str(value.iloc[0]) if len(value) > 0 else 'EMPTY'
            log_entry['last_value'] = str(value.iloc[-1]) if len(value) > 0 else 'EMPTY'
            log_entry['null_count'] = value.isna().sum()
        
        self.conversion_log.append(log_entry)
        
        # Print to console for real-time debugging
        print(f"\n{'='*80}")
        print(f"[TIMESTAMP DIAGNOSTIC] Stage: {stage}")
        print(f"Description: {description}")
        print(f"Value Type: {log_entry['value_type']}")
        
        for key, val in log_entry.items():
            if key not in ['stage', 'description', 'value', 'value_type', 'additional_info']:
                print(f"  {key}: {val}")
        
        if additional_info:
            print("Additional Info:")
            for key, val in additional_info.items():
                print(f"  {key}: {val}")
        print(f"{'='*80}\n")
        
    def compare_timestamps(self, label, ts1, ts2):
        """Compare two timestamps and log the differences."""
        if not self.enable_logging:
            return
            
        print(f"\n[TIMESTAMP COMPARE] {label}")
        print(f"  Timestamp 1: {ts1} (type: {type(ts1).__name__})")
        print(f"  Timestamp 2: {ts2} (type: {type(ts2).__name__})")
        
        # Try to convert both to comparable format
        try:
            if isinstance(ts1, (int, float)) and isinstance(ts2, (int, float)):
                diff = ts2 - ts1
                print(f"  Difference (numeric): {diff}")
            elif hasattr(ts1, 'timestamp') and hasattr(ts2, 'timestamp'):
                t1_unix = ts1.timestamp()
                t2_unix = ts2.timestamp()
                diff = t2_unix - t1_unix
                print(f"  Timestamp 1 (Unix): {t1_unix}")
                print(f"  Timestamp 2 (Unix): {t2_unix}")
                print(f"  Difference (seconds): {diff}")
            else:
                print(f"  Unable to compare (incompatible types)")
        except Exception as e:
            print(f"  Comparison error: {e}")
    
    def verify_range_selection(self, original_df, filtered_df, start_time, end_time):
        """Verify that filtered data matches the selected range."""
        print(f"\n{'='*80}")
        print("[RANGE SELECTION VERIFICATION]")
        print(f"{'='*80}")
        
        # Original data info
        print(f"\nOriginal Data:")
        print(f"  Total rows: {len(original_df)}")
        if 'Timestamp' in original_df.columns:
            print(f"  Timestamp dtype: {original_df['Timestamp'].dtype}")
            print(f"  First timestamp: {original_df['Timestamp'].iloc[0]}")
            print(f"  Last timestamp: {original_df['Timestamp'].iloc[-1]}")
            print(f"  Time range: {original_df['Timestamp'].iloc[-1] - original_df['Timestamp'].iloc[0]}")
        
        # Filtered data info
        print(f"\nFiltered Data:")
        print(f"  Total rows: {len(filtered_df)}")
        if 'Timestamp' in filtered_df.columns:
            print(f"  Timestamp dtype: {filtered_df['Timestamp'].dtype}")
            if len(filtered_df) > 0:
                print(f"  First timestamp: {filtered_df['Timestamp'].iloc[0]}")
                print(f"  Last timestamp: {filtered_df['Timestamp'].iloc[-1]}")
                print(f"  Time range: {filtered_df['Timestamp'].iloc[-1] - filtered_df['Timestamp'].iloc[0]}")
            else:
                print(f"  ERROR: Filtered dataframe is EMPTY!")
        
        # Selected range info
        print(f"\nSelected Range:")
        print(f"  Start: {start_time} (type: {type(start_time).__name__})")
        print(f"  End: {end_time} (type: {type(end_time).__name__})")
        if hasattr(start_time, 'timestamp') and hasattr(end_time, 'timestamp'):
            duration = end_time.timestamp() - start_time.timestamp()
            print(f"  Duration (seconds): {duration}")
        
        # Verification checks
        print(f"\nVerification:")
        if len(filtered_df) == 0:
            print(f"  [ERROR] FAIL: Filtered data is empty!")
        elif 'Timestamp' not in filtered_df.columns:
            print(f"  [ERROR] FAIL: No Timestamp column in filtered data!")
        else:
            first_ts = pd.to_datetime(filtered_df['Timestamp'].iloc[0])
            last_ts = pd.to_datetime(filtered_df['Timestamp'].iloc[-1])
            start_pd = pd.to_datetime(start_time)
            end_pd = pd.to_datetime(end_time)
            
            # Check if filtered data is within selected range
            if first_ts >= start_pd:
                print(f"  [OK] First timestamp is after or equal to start")
            else:
                print(f"  [ERROR] First timestamp ({first_ts}) is BEFORE start ({start_pd})")
                print(f"     Difference: {(start_pd - first_ts).total_seconds()} seconds")
            
            if last_ts <= end_pd:
                print(f"  [OK] Last timestamp is before or equal to end")
            else:
                print(f"  [ERROR] Last timestamp ({last_ts}) is AFTER end ({end_pd})")
                print(f"     Difference: {(last_ts - end_pd).total_seconds()} seconds")
            
            # Check for data outside range
            outside_range = filtered_df[
                (pd.to_datetime(filtered_df['Timestamp']) < start_pd) |
                (pd.to_datetime(filtered_df['Timestamp']) > end_pd)
            ]
            if len(outside_range) == 0:
                print(f"  [OK] All data points are within selected range")
            else:
                print(f"  [ERROR] {len(outside_range)} data points are OUTSIDE the selected range!")
            
            # Check for missing data within range
            original_in_range = original_df[
                (pd.to_datetime(original_df['Timestamp']) >= start_pd) &
                (pd.to_datetime(original_df['Timestamp']) <= end_pd)
            ]
            if len(original_in_range) == len(filtered_df):
                print(f"  [OK] All expected data points are present ({len(filtered_df)} points)")
            else:
                print(f"  [ERROR] Missing data! Expected {len(original_in_range)} points, got {len(filtered_df)} points")
                print(f"     Missing: {len(original_in_range) - len(filtered_df)} points")
        
        print(f"{'='*80}\n")
    
    def export_log(self, filename='timestamp_diagnostic_log.txt'):
        """Export the conversion log to a file."""
        with open(filename, 'w') as f:
            f.write("TIMESTAMP CONVERSION DIAGNOSTIC LOG\n")
            f.write("="*80 + "\n\n")
            
            for i, entry in enumerate(self.conversion_log, 1):
                f.write(f"Entry #{i}\n")
                f.write(f"Stage: {entry['stage']}\n")
                f.write(f"Description: {entry['description']}\n")
                for key, val in entry.items():
                    if key not in ['stage', 'description']:
                        f.write(f"  {key}: {val}\n")
                f.write("\n" + "-"*80 + "\n\n")
        
        print(f"Diagnostic log exported to: {filename}")

# Global diagnostics instance
_diagnostics = None

def get_diagnostics(enable=True):
    """Get or create the global diagnostics instance."""
    global _diagnostics
    if _diagnostics is None:
        _diagnostics = TimestampDiagnostics(enable_logging=enable)
    return _diagnostics

def log_conversion(stage, description, value, **kwargs):
    """Convenience function for logging conversions."""
    diag = get_diagnostics()
    diag.log_conversion(stage, description, value, kwargs)

def compare_timestamps(label, ts1, ts2):
    """Convenience function for comparing timestamps."""
    diag = get_diagnostics()
    diag.compare_timestamps(label, ts1, ts2)

def verify_range_selection(original_df, filtered_df, start_time, end_time):
    """Convenience function for verifying range selection."""
    diag = get_diagnostics()
    diag.verify_range_selection(original_df, filtered_df, start_time, end_time)

def export_log(filename='timestamp_diagnostic_log.txt'):
    """Convenience function for exporting log."""
    diag = get_diagnostics()
    diag.export_log(filename)
