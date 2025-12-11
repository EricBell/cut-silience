"""
CLI parser and main entry point for Cut-Silence.
"""

import argparse
import sys
import tempfile
import shutil
import json
from pathlib import Path
from typing import List

from cut_silence.config import (
    DEFAULT_SILENCE_THRESHOLD,
    DEFAULT_MIN_SILENCE_DURATION,
    DEFAULT_PADDING,
    OUTPUT_SUFFIX,
)
from cut_silence.analyzer import VideoAnalyzer
from cut_silence.processor import SegmentProcessor
from cut_silence.concatenator import VideoConcatenator
from cut_silence.progress import ProgressReporter


def parse_arguments(args: List[str] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="cut-silence",
        description="Automatically remove silence from MP4 videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cut-silence video.mp4                     # Process single video
  cut-silence *.mp4                         # Process multiple videos
  cut-silence video.mp4 --threshold -35     # Custom silence threshold
  cut-silence video.mp4 --padding 0.3       # Add padding around speech
  cut-silence video.mp4 --first-minutes 5   # Process first 5 minutes only
  cut-silence video.mp4 --dry-run           # Preview without processing
        """,
    )

    parser.add_argument(
        "input_files",
        nargs="+",
        type=Path,
        help="Input video file(s) to process",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path (only valid for single input file)",
    )

    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=DEFAULT_SILENCE_THRESHOLD,
        help=f"Silence threshold in dB (default: {DEFAULT_SILENCE_THRESHOLD})",
    )

    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=DEFAULT_MIN_SILENCE_DURATION,
        help=f"Minimum silence duration in seconds (default: {DEFAULT_MIN_SILENCE_DURATION})",
    )

    parser.add_argument(
        "-p",
        "--padding",
        type=float,
        default=DEFAULT_PADDING,
        help=f"Padding around speech in seconds (default: {DEFAULT_PADDING})",
    )

    parser.add_argument(
        "--first-minutes",
        type=float,
        help="Process only the first N minutes of the video",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without processing",
    )

    parser.add_argument(
        "--export-segments",
        type=Path,
        help="Export segment timestamps to JSON file",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser.parse_args(args)


def validate_arguments(args: argparse.Namespace) -> None:
    """Validate parsed arguments."""
    # Check if output is specified with multiple input files
    if args.output and len(args.input_files) > 1:
        print("Error: --output can only be used with a single input file", file=sys.stderr)
        sys.exit(1)

    # Validate first-minutes argument
    if hasattr(args, 'first_minutes') and args.first_minutes is not None:
        if args.first_minutes <= 0:
            print("Error: --first-minutes must be a positive number", file=sys.stderr)
            sys.exit(1)

    # Check if all input files exist
    for input_file in args.input_files:
        if not input_file.exists():
            print(f"Error: Input file not found: {input_file}", file=sys.stderr)
            sys.exit(1)

        if not input_file.is_file():
            print(f"Error: Not a file: {input_file}", file=sys.stderr)
            sys.exit(1)


def process_video(
    input_file: Path,
    output_file: Path,
    threshold: float,
    min_duration: float,
    padding: float,
    verbose: bool,
    dry_run: bool,
    export_segments_path: Path = None,
    first_minutes: float = None,
) -> bool:
    """
    Process a single video file to remove silence.

    Returns:
        True if processing was successful, False otherwise
    """
    print(f"\nProcessing: {input_file}")

    # Calculate max duration if first_minutes is specified
    max_duration = None
    if first_minutes is not None:
        max_duration = first_minutes * 60.0  # Convert minutes to seconds
        if verbose:
            print(f"Processing first {first_minutes} minutes ({max_duration:.1f}s) only")

    # Initialize components
    analyzer = VideoAnalyzer(threshold, min_duration, verbose, max_duration)
    processor = SegmentProcessor(verbose)
    concatenator = VideoConcatenator(verbose)
    reporter = ProgressReporter(verbose)

    try:
        # Step 1: Get video duration
        if verbose:
            print("Getting video duration...")
        total_duration = analyzer.get_video_duration(input_file)
        if verbose:
            print(f"Video duration: {total_duration:.2f}s")

        # Check if first_minutes exceeds video duration
        if max_duration is not None and max_duration > total_duration:
            print(f"Warning: --first-minutes ({first_minutes:.1f}m) exceeds video duration ({total_duration/60:.1f}m)")
            print(f"Processing entire video instead")
            max_duration = None

        # Step 2: Detect silence
        if verbose:
            print("Detecting silence...")
        silent_segments = analyzer.detect_silence(input_file, show_progress=True)

        # Step 3: Calculate non-silent segments
        non_silent_segments = analyzer.calculate_non_silent_segments(
            silent_segments, total_duration, padding
        )

        if verbose or dry_run:
            print(f"\nFound {len(silent_segments)} silent segment(s)")
            print(f"Keeping {len(non_silent_segments)} non-silent segment(s)")

        # Export segments if requested
        if export_segments_path:
            export_data = {
                "input_file": str(input_file),
                "total_duration": total_duration,
                "silent_segments": silent_segments,
                "non_silent_segments": non_silent_segments,
            }
            with open(export_segments_path, 'w') as f:
                json.dump(export_data, f, indent=2)
            if verbose:
                print(f"Exported segments to: {export_segments_path}")

        # Calculate statistics
        silence_duration = sum(end - start for start, end in silent_segments)
        output_duration = sum(end - start for start, end in non_silent_segments)

        if dry_run:
            print(f"\nDry-run preview:")
            if max_duration is not None:
                print(f"  Processing duration: {reporter._format_time(max_duration)} (limited)")
                print(f"  Original duration:   {reporter._format_time(total_duration)}")
            else:
                print(f"  Original duration:   {reporter._format_time(total_duration)}")
            print(f"  Silence detected:    {reporter._format_time(silence_duration)}")
            print(f"  Output duration:     {reporter._format_time(output_duration)}")
            effective_total = max_duration if max_duration is not None else total_duration
            reduction = (silence_duration / effective_total * 100) if effective_total > 0 else 0
            print(f"  Reduction:           {reduction:.1f}%")
            print(f"\nOutput would be saved to: {output_file}")
            return True

        # Check if there's anything to process
        if not non_silent_segments:
            print("\nWarning: No non-silent segments found.")
            print("The video appears to be entirely silent or audio is very quiet.")
            print(f"Try adjusting the threshold (current: {threshold}dB)")
            print("Suggestion: Use a lower threshold like -40dB or -50dB")
            print("Example: cut-silence input.mp4 --threshold -40")
            return False

        # Step 4: Extract segments
        if verbose:
            print("Extracting segments...")

        temp_dir = Path(tempfile.mkdtemp(prefix="cut_silence_"))
        try:
            segment_files = processor.extract_segments(
                input_file, non_silent_segments, temp_dir, show_progress=True
            )

            if not segment_files:
                print("Error: Failed to extract segments")
                return False

            # Step 5: Concatenate segments
            if verbose:
                print("Concatenating segments...")

            success = concatenator.concatenate_segments(segment_files, output_file, show_progress=True)

            if success:
                reporter.print_summary(total_duration, output_duration, len(silent_segments))
                print(f"✓ Saved to: {output_file}")
                return True
            else:
                print("Error: Failed to concatenate segments")
                return False

        finally:
            # Clean up temporary directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    except Exception as e:
        print(f"Error processing {input_file}: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def main():
    """Main entry point for Cut-Silence CLI."""
    args = parse_arguments()
    validate_arguments(args)

    if args.verbose:
        print(f"Cut-Silence v0.1.0")
        print(f"Processing {len(args.input_files)} file(s)...")
        print(f"Silence threshold: {args.threshold} dB")
        print(f"Min silence duration: {args.duration}s")
        print(f"Padding: {args.padding}s")
        if hasattr(args, 'first_minutes') and args.first_minutes is not None:
            print(f"First minutes: {args.first_minutes}")
        print(f"Dry-run: {args.dry_run}")
        print()

    # Initialize concatenator for output path generation
    concatenator = VideoConcatenator(args.verbose)

    success_count = 0
    failure_count = 0

    for input_file in args.input_files:
        # Determine output file path
        if args.output:
            output_file = args.output
        else:
            output_file = concatenator.generate_output_path(input_file, OUTPUT_SUFFIX)

        # Process the video
        success = process_video(
            input_file=input_file,
            output_file=output_file,
            threshold=args.threshold,
            min_duration=args.duration,
            padding=args.padding,
            verbose=args.verbose,
            dry_run=args.dry_run,
            export_segments_path=args.export_segments,
            first_minutes=getattr(args, 'first_minutes', None),
        )

        if success:
            success_count += 1
        else:
            failure_count += 1

    # Print final summary
    print(f"\n{'='*50}")
    print(f"Processing complete!")
    print(f"  Successful: {success_count}")
    print(f"  Failed:     {failure_count}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
