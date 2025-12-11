"""
Segment processor module for handling video segments.
"""

from pathlib import Path
from typing import List, Tuple
import subprocess
from tqdm import tqdm

from cut_silence.ffmpeg_runner import FFmpegProgressRunner


class SegmentProcessor:
    """Processes video segments for concatenation."""

    def __init__(self, verbose: bool = False):
        """
        Initialize segment processor.

        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose

    def extract_segments(
        self, video_path: Path, segments: List[Tuple[float, float]], temp_dir: Path, show_progress: bool = True
    ) -> List[Path]:
        """
        Extract non-silent segments from video.

        Args:
            video_path: Path to the input video file
            segments: List of (start, end) tuples for segments to extract
            temp_dir: Temporary directory for segment files
            show_progress: Whether to show progress bar

        Returns:
            List of paths to extracted segment files
        """
        if self.verbose:
            print(f"Extracting {len(segments)} segments from: {video_path}")

        # Create temp directory if it doesn't exist
        temp_dir.mkdir(parents=True, exist_ok=True)

        segment_files = []
        runner = FFmpegProgressRunner()

        # Outer progress bar for segment count
        with tqdm(
            total=len(segments),
            desc="Extracting segments",
            unit="segment",
            disable=not show_progress,
            position=0
        ) as segment_bar:
            for idx, (start_time, end_time) in enumerate(segments):
                segment_file = temp_dir / f"segment_{idx:04d}.mp4"

                # Calculate duration
                duration = end_time - start_time

                # Ensure segment doesn't exceed any time limits
                if duration <= 0:
                    if self.verbose:
                        print(f"Skipping invalid segment {idx} (duration: {duration:.3f}s)")
                    continue

                # Use FFmpeg to extract segment with stream copy (no re-encoding for speed)
                # IMPORTANT: -ss MUST be before -i when using -c copy to preserve video stream
                # This is fast but seeks to nearest keyframe (slightly less accurate)
                cmd = [
                    "ffmpeg",
                    "-y",  # Overwrite output files
                    "-ss", str(start_time),  # Start time (BEFORE -i for fast seek with copy)
                    "-i", str(video_path),  # Input file
                    "-t", str(duration),  # Duration to extract
                    "-map", "0",  # Map all streams from input
                    "-c", "copy",  # Copy all streams (no re-encoding)
                    "-avoid_negative_ts", "make_zero",  # Fix timestamp issues
                    str(segment_file)
                ]

                # Run FFmpeg without individual segment progress (just use outer counter)
                result = runner.run_with_progress(
                    cmd=cmd,
                    description=f"  Segment {idx+1}/{len(segments)}",
                    total_duration=duration,
                    show_progress=False  # Disable inner progress, rely on outer segment counter
                )

                if result.returncode == 0 and segment_file.exists():
                    segment_files.append(segment_file)
                else:
                    if self.verbose:
                        print(f"Warning: Failed to extract segment {idx}")

                # Update outer progress bar
                segment_bar.update(1)

        if self.verbose:
            print(f"Successfully extracted {len(segment_files)} segments")

        return segment_files

    def validate_segments(self, segment_files: List[Path]) -> bool:
        """
        Validate that all segment files were created successfully.

        Args:
            segment_files: List of segment file paths

        Returns:
            True if all segments are valid, False otherwise
        """
        # TODO: Implement validation
        return all(f.exists() and f.stat().st_size > 0 for f in segment_files)
