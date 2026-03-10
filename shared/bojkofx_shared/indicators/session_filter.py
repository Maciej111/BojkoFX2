"""
Session Filter - London and New York trading sessions.
"""
import pandas as pd


def is_in_session(timestamp, session_mode='both'):
    """
    Check if timestamp is within specified trading session(s).
    
    Sessions (UTC):
    - London: 08:00 - 16:59
    - New York: 13:00 - 21:59
    
    Args:
        timestamp: pandas Timestamp
        session_mode: 'london', 'ny', or 'both'
    
    Returns:
        bool: True if in session, False otherwise
    """
    # Get UTC hour
    hour = timestamp.hour
    
    # Define sessions
    london_start = 8
    london_end = 17  # 16:59 = up to hour 16
    ny_start = 13
    ny_end = 22  # 21:59 = up to hour 21
    
    if session_mode == 'london':
        return london_start <= hour < london_end
    elif session_mode == 'ny':
        return ny_start <= hour < ny_end
    elif session_mode == 'both':
        # London OR NY
        in_london = london_start <= hour < london_end
        in_ny = ny_start <= hour < ny_end
        return in_london or in_ny
    else:
        # Invalid mode - allow all
        return True


def get_session_name(timestamp):
    """
    Get the current session name for a timestamp.
    
    Returns:
        str: 'London', 'NY', 'Overlap', 'Asian', or 'Off-hours'
    """
    hour = timestamp.hour
    
    london_active = 8 <= hour < 17
    ny_active = 13 <= hour < 22
    
    if london_active and ny_active:
        return 'Overlap'
    elif london_active:
        return 'London'
    elif ny_active:
        return 'NY'
    elif 0 <= hour < 8:
        return 'Asian'
    else:
        return 'Off-hours'

