"""
Video concatenator module for joining video segments.
"""

from pathlib import Path
from typing import List
import subprocess
import tempfile


class VideoConcatenator:
    """Concatenates video segments into a single output file."""

    def __init__(self, verbose: bool = False):
        """
        Initialize video concatenator.

        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose

    def concatenate_segments(
        self, segment_files: List[Path], output_path: Path
    ) -> bool:
        """
        Concatenate video segments into a single file.

        Args:
            segment_files: List of segment file paths to concatenate
            output_path: Path for the output video file

        Returns:
            True if concatenation was successful, False otherwise
        """
        if self.verbose:
            print(f"Concatenating {len(segment_files)} segments to: {output_path}")

        if not segment_files:
            if self.verbose:
                print("No segments to concatenate")
            return False

        # If only one segment, just copy it
        if len(segment_files) == 1:
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(segment_files[0]),
                "-map", "0",
                "-c", "copy",
                str(output_path)
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            success = result.returncode == 0 and output_path.exists()

            if self.verbose:
                if success:
                    print(f"Successfully created: {output_path}")
                else:
                    print(f"Failed to copy segment")
                    print(f"FFmpeg stderr: {result.stderr[-500:]}")  # Last 500 chars

            return success

        # Create a temporary concat file list
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            concat_file = Path(f.name)
            for segment_file in segment_files:
                # Use absolute paths and escape special characters
                abs_path = segment_file.resolve()
                f.write(f"file '{abs_path}'\n")

        try:
            # Use FFmpeg concat demuxer to join segments
            cmd = [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-map", "0",
                "-c", "copy",
                str(output_path)
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            success = result.returncode == 0 and output_path.exists()

            if self.verbose:
                if success:
                    print(f"Successfully created: {output_path}")
                else:
                    print(f"Failed to concatenate segments")
                    print(f"FFmpeg stderr: {result.stderr[-500:]}")  # Last 500 chars

            return success

        finally:
            # Clean up temporary concat file
            if concat_file.exists():
                concat_file.unlink()

    def generate_output_path(self, input_path: Path, suffix: str = "_cut") -> Path:
        """
        Generate output file path with auto-rename on collision.

        Args:
            input_path: Input video file path
            suffix: Suffix to add to filename

        Returns:
            Output file path (with collision handling)
        """
        stem = input_path.stem
        ext = input_path.suffix
        parent = input_path.parent

        # Generate base output path
        output_path = parent / f"{stem}{suffix}{ext}"

        # Handle file collision with auto-rename
        counter = 1
        while output_path.exists():
            output_path = parent / f"{stem}{suffix}_{counter}{ext}"
            counter += 1

        return output_path
