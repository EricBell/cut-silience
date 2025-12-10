"""
Video analyzer module for detecting silence in videos.
"""

from pathlib import Path
from typing import List, Tuple
import subprocess
import json


class VideoAnalyzer:
    """Analyzes videos to detect silent segments."""

    def __init__(self, threshold: float, min_duration: float, verbose: bool = False):
        """
        Initialize video analyzer.

        Args:
            threshold: Silence threshold in dB
            min_duration: Minimum silence duration in seconds
            verbose: Enable verbose output
        """
        self.threshold = threshold
        self.min_duration = min_duration
        self.verbose = verbose

    def detect_silence(self, video_path: Path) -> List[Tuple[float, float]]:
        """
        Detect silent segments in the video.

        Args:
            video_path: Path to the video file

        Returns:
            List of tuples (start_time, end_time) representing silent segments
        """
        if self.verbose:
            print(f"Analyzing silence in: {video_path}")

        # Use FFmpeg's silencedetect filter to find silent segments
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-af", f"silencedetect=noise={self.threshold}dB:d={self.min_duration}",
            "-f", "null",
            "-"
        ]

        # Run FFmpeg and capture stderr (where silencedetect outputs)
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Parse the output to extract silence segments
        silent_segments = []
        silence_start = None

        for line in result.stderr.split('\n'):
            if 'silencedetect' in line:
                if 'silence_start' in line:
                    # Extract start time
                    parts = line.split('silence_start: ')
                    if len(parts) > 1:
                        silence_start = float(parts[1].strip().split()[0])
                elif 'silence_end' in line and silence_start is not None:
                    # Extract end time
                    parts = line.split('silence_end: ')
                    if len(parts) > 1:
                        silence_end = float(parts[1].strip().split()[0])
                        silent_segments.append((silence_start, silence_end))
                        silence_start = None

        if self.verbose:
            print(f"Found {len(silent_segments)} silent segments")

        return silent_segments

    def get_video_duration(self, video_path: Path) -> float:
        """
        Get the total duration of the video.

        Args:
            video_path: Path to the video file

        Returns:
            Duration in seconds
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path)
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        return duration

    def calculate_non_silent_segments(
        self, silent_segments: List[Tuple[float, float]], total_duration: float, padding: float = 0.0, min_segment_duration: float = 0.1
    ) -> List[Tuple[float, float]]:
        """
        Calculate non-silent segments from silent segments.

        Args:
            silent_segments: List of (start, end) tuples for silent segments
            total_duration: Total video duration in seconds
            padding: Padding to add around speech in seconds
            min_segment_duration: Minimum duration for a segment to be included (default: 0.1s)

        Returns:
            List of (start, end) tuples for non-silent segments
        """
        if not silent_segments:
            # No silence detected, return entire video
            return [(0.0, total_duration)]

        non_silent_segments = []
        current_time = 0.0

        for silence_start, silence_end in silent_segments:
            # Add padding around silence (shrink the silent region)
            adjusted_start = max(0.0, silence_start + padding)
            adjusted_end = min(total_duration, silence_end - padding)

            # Only add non-silent segment if there's actual content and it meets minimum duration
            if current_time < adjusted_start:
                duration = adjusted_start - current_time
                if duration >= min_segment_duration:
                    non_silent_segments.append((current_time, adjusted_start))
                elif self.verbose:
                    print(f"Skipping short segment ({duration:.3f}s) from {current_time:.2f}s to {adjusted_start:.2f}s")

            current_time = adjusted_end

        # Add final segment if there's content after last silence
        if current_time < total_duration:
            duration = total_duration - current_time
            if duration >= min_segment_duration:
                non_silent_segments.append((current_time, total_duration))
            elif self.verbose:
                print(f"Skipping short segment ({duration:.3f}s) from {current_time:.2f}s to {total_duration:.2f}s")

        return non_silent_segments
