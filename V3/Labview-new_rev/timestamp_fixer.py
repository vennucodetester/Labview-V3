"""
Timestamp Fixer Utility
Handles common timestamp parsing issues and provides intelligent date correction
"""

import pandas as pd
from datetime import datetime, timedelta
import re

class TimestampFixer:
    """Utility class for fixing common timestamp parsing issues."""
    
    def __init__(self):
        self.current_year = datetime.now().year
        
    def fix_ambiguous_dates(self, date_series, time_series=None):
        """
        Fix ambiguous dates that might be parsed incorrectly.
        
        Args:
            date_series: pandas Series of date strings
            time_series: pandas Series of time strings (optional)
            
        Returns:
            pandas Series of corrected datetime objects
        """
        print(f"[TIMESTAMP_FIXER] Analyzing {len(date_series)} date entries...")
        
        # Sample the data to understand the format
        sample_dates = date_series.head(10).tolist()
        print(f"[TIMESTAMP_FIXER] Sample dates: {sample_dates}")
        
        # Detect common date patterns
        date_patterns = self._detect_date_patterns(sample_dates)
        print(f"[TIMESTAMP_FIXER] Detected patterns: {date_patterns}")
        
        # Create combined timestamp strings if time series is provided
        if time_series is not None:
            timestamp_str = date_series.astype(str) + ' ' + time_series.astype(str)
        else:
            timestamp_str = date_series.astype(str)
        
        # Try different parsing strategies
        timestamps = self._parse_with_strategies(timestamp_str, date_patterns)
        
        # Validate and correct if needed
        timestamps = self._validate_and_correct_timestamps(timestamps)
        
        # CRITICAL FIX: Ensure timestamps are naive (no timezone) to match CSV display
        if timestamps.dt.tz is not None:
            print(f"[TIMESTAMP_FIXER] Converting timezone-aware timestamps to naive (local time)")
            timestamps = timestamps.dt.tz_localize(None)
        
        return timestamps
    
    def _detect_date_patterns(self, sample_dates):
        """Detect common date patterns in the sample data."""
        patterns = {
            'has_four_digit_year': False,
            'has_two_digit_year': False,
            'uses_slashes': False,
            'uses_dashes': False,
            'uses_spaces': False,
            'future_years': [],
            'year_range': None
        }
        
        for date_str in sample_dates:
            if re.search(r'/\d{4}/', str(date_str)) or re.search(r'-\d{4}-', str(date_str)):
                patterns['has_four_digit_year'] = True
            if re.search(r'/\d{2}/', str(date_str)) or re.search(r'-\d{2}-', str(date_str)):
                patterns['has_two_digit_year'] = True
            if '/' in str(date_str):
                patterns['uses_slashes'] = True
            if '-' in str(date_str):
                patterns['uses_dashes'] = True
            if ' ' in str(date_str):
                patterns['uses_spaces'] = True
                
            # Extract year if possible
            year_match = re.search(r'(\d{4})', str(date_str))
            if year_match:
                year = int(year_match.group(1))
                if year > self.current_year:
                    patterns['future_years'].append(year)
        
        if patterns['future_years']:
            patterns['year_range'] = (min(patterns['future_years']), max(patterns['future_years']))
        
        return patterns
    
    def _parse_with_strategies(self, timestamp_str, patterns):
        """Try different parsing strategies based on detected patterns."""
        strategies = []
        
        # Strategy 1: Parse as-is
        try:
            timestamps = pd.to_datetime(timestamp_str, errors='coerce')
            if not timestamps.isna().all():
                strategies.append(('as_is', timestamps))
                print(f"[TIMESTAMP_FIXER] Strategy 'as_is' succeeded")
        except Exception as e:
            print(f"[TIMESTAMP_FIXER] Strategy 'as_is' failed: {e}")
        
        # Strategy 2: Handle future years
        if patterns['future_years']:
            try:
                # Try correcting the year to current year
                corrected_str = timestamp_str.str.replace(
                    r'/(\d{4})', f'/{self.current_year}', regex=True
                )
                corrected_str = corrected_str.str.replace(
                    r'-(\d{4})-', f'-{self.current_year}-', regex=True
                )
                timestamps = pd.to_datetime(corrected_str, errors='coerce')
                if not timestamps.isna().all():
                    strategies.append(('year_corrected', timestamps))
                    print(f"[TIMESTAMP_FIXER] Strategy 'year_corrected' succeeded")
            except Exception as e:
                print(f"[TIMESTAMP_FIXER] Strategy 'year_corrected' failed: {e}")
        
        # Strategy 3: Explicit format parsing
        if patterns['uses_slashes']:
            try:
                timestamps = pd.to_datetime(timestamp_str, format='%m/%d/%Y %H:%M:%S', errors='coerce')
                if not timestamps.isna().all():
                    strategies.append(('explicit_slash', timestamps))
                    print(f"[TIMESTAMP_FIXER] Strategy 'explicit_slash' succeeded")
            except Exception as e:
                print(f"[TIMESTAMP_FIXER] Strategy 'explicit_slash' failed: {e}")
        
        # Strategy 4: Try different year assumptions
        for assumed_year in [2024, 2023, 2022]:
            try:
                year_corrected_str = timestamp_str.str.replace(
                    r'/(\d{4})', f'/{assumed_year}', regex=True
                )
                timestamps = pd.to_datetime(year_corrected_str, errors='coerce')
                if not timestamps.isna().all():
                    strategies.append((f'year_{assumed_year}', timestamps))
                    print(f"[TIMESTAMP_FIXER] Strategy 'year_{assumed_year}' succeeded")
            except Exception as e:
                print(f"[TIMESTAMP_FIXER] Strategy 'year_{assumed_year}' failed: {e}")
        
        # Choose the best strategy
        if not strategies:
            print(f"[TIMESTAMP_FIXER] All strategies failed, using default parsing")
            return pd.to_datetime(timestamp_str, errors='coerce')
        
        # Prefer strategies that don't have future dates
        best_strategy = None
        for strategy_name, timestamps in strategies:
            if not timestamps.dropna().empty:
                sample_ts = timestamps.dropna().iloc[0]
                if sample_ts.year <= self.current_year:
                    best_strategy = (strategy_name, timestamps)
                    break
        
        if best_strategy is None:
            # Fallback to first successful strategy
            best_strategy = strategies[0]
        
        print(f"[TIMESTAMP_FIXER] Selected strategy: {best_strategy[0]}")
        return best_strategy[1]
    
    def _validate_and_correct_timestamps(self, timestamps):
        """Validate timestamps and apply final corrections if needed."""
        if timestamps.dropna().empty:
            print(f"[TIMESTAMP_FIXER] No valid timestamps found")
            return timestamps
        
        # Check for reasonable date range
        first_ts = timestamps.dropna().iloc[0]
        last_ts = timestamps.dropna().iloc[-1]
        
        print(f"[TIMESTAMP_FIXER] Timestamp range: {first_ts} to {last_ts}")
        print(f"[TIMESTAMP_FIXER] Duration: {last_ts - first_ts}")
        
        # Check if dates are in the future
        if first_ts.year > self.current_year + 1:
            print(f"[TIMESTAMP_FIXER] WARNING: Data appears to be from future year {first_ts.year}")
            print(f"[TIMESTAMP_FIXER] This may indicate incorrect year parsing")
            
            # Try to correct by subtracting years
            if first_ts.year > 2024:
                years_to_subtract = first_ts.year - 2024
                print(f"[TIMESTAMP_FIXER] Attempting to subtract {years_to_subtract} years")
                corrected_timestamps = timestamps - pd.DateOffset(years=years_to_subtract)
                
                # Verify the correction
                corrected_first = corrected_timestamps.dropna().iloc[0]
                if corrected_first.year <= 2024:
                    print(f"[TIMESTAMP_FIXER] Year correction successful: {corrected_first.year}")
                    return corrected_timestamps
                else:
                    print(f"[TIMESTAMP_FIXER] Year correction failed")
        
        return timestamps

# Global instance
_timestamp_fixer = None

def get_timestamp_fixer():
    """Get or create the global timestamp fixer instance."""
    global _timestamp_fixer
    if _timestamp_fixer is None:
        _timestamp_fixer = TimestampFixer()
    return _timestamp_fixer

def fix_ambiguous_dates(date_series, time_series=None):
    """Convenience function for fixing ambiguous dates."""
    fixer = get_timestamp_fixer()
    return fixer.fix_ambiguous_dates(date_series, time_series)
