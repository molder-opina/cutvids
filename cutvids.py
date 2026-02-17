#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import glob


def run_cmd(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result


def get_duration(file_path):
    result = run_cmd(
        f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{file_path}"'
    )
    return float(result.stdout.strip())


def transcribe(input_file, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    model = "small"
    lang = "es"

    cmd = f'whisper "{input_file}" --language {lang} --output_format srt --output_dir "{output_dir}" --model {model}'
    print(f"Transcribing: {cmd}")
    run_cmd(cmd)

    srt_files = glob.glob(f"{output_dir}/*.srt")
    if not srt_files:
        print("No SRT file generated", file=sys.stderr)
        sys.exit(1)
    return srt_files[0]


def parse_srt(srt_path):
    subtitles = []
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0])
            time_line = lines[1]
            text = " ".join(lines[2:])

            start_time = time_line.split(" --> ")[0]
            end_time = time_line.split(" --> ")[1]

            start_sec = parse_time(start_time)
            end_sec = parse_time(end_time)

            subtitles.append(
                {"index": idx, "start": start_sec, "end": end_sec, "text": text}
            )
        except:
            continue

    return subtitles


def parse_time(time_str):
    parts = time_str.replace(",", ".").split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def find_occurrences(subtitles, search_term):
    search_lower = search_term.lower()
    occurrences = []

    for sub in subtitles:
        if search_lower in sub["text"].lower():
            mid_time = (sub["start"] + sub["end"]) / 2
            occurrences.append(
                {
                    "time": mid_time,
                    "text": sub["text"],
                    "start": sub["start"],
                    "end": sub["end"],
                }
            )

    return occurrences


def extract_clips(input_file, occurrences, before_sec, after_sec, cuts_dir):
    os.makedirs(cuts_dir, exist_ok=True)

    duration = get_duration(input_file)
    clip_paths = []

    for i, occ in enumerate(occurrences):
        start_time = max(0, occ["time"] - before_sec)
        end_time = min(duration, occ["time"] + after_sec)
        duration_clip = end_time - start_time

        output_clip = f"{cuts_dir}/clip_{i:04d}.mp4"

        cmd = f'ffmpeg -y -i "{input_file}" -ss {start_time} -t {duration_clip} -c:v libx264 -c:a aac -avoid_negative_ts make_zero "{output_clip}"'
        print(f"Extracting clip {i + 1}/{len(occurrences)}: {output_clip}")
        run_cmd(cmd)
        clip_paths.append(output_clip)

    return clip_paths


def concat_clips(clip_paths, output_file):
    list_file = "/tmp/concat_list.txt"
    with open(list_file, "w") as f:
        for path in clip_paths:
            f.write(f"file '{path}'\n")

    cmd = f'ffmpeg -y -f concat -safe 0 -i "{list_file}" -c copy "{output_file}"'
    print(f"Concatenating to: {output_file}")
    run_cmd(cmd)

    os.remove(list_file)


def main():
    parser = argparse.ArgumentParser(
        description="Extract audio/video clips containing a search term"
    )
    parser.add_argument("input", help="Input video or audio file")
    parser.add_argument("search", help="Word or phrase to search for")
    parser.add_argument(
        "--before", type=float, default=1, help="Seconds before occurrence (default: 1)"
    )
    parser.add_argument(
        "--after", type=float, default=1, help="Seconds after occurrence (default: 1)"
    )
    parser.add_argument(
        "--workspace", default="/Volumes/KINGSTON/spaces", help="Workspace directory"
    )
    parser.add_argument("--cuts-dir", default=None, help="Directory for cuts")
    parser.add_argument("--output", default=None, help="Output file name")

    args = parser.parse_args()

    input_file = args.input
    if not os.path.exists(input_file):
        print(f"Input file not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    base_name = os.path.splitext(os.path.basename(input_file))[0]
    workspace = args.workspace

    transcribe_dir = os.path.join(workspace, "transcribe_temp")
    cuts_dir = args.cuts_dir or os.path.join(workspace, f"cuts_{base_name}")

    print(f"Transcribing: {input_file}")
    srt_file = transcribe(input_file, transcribe_dir)

    print(f"Parsing subtitles: {srt_file}")
    subtitles = parse_srt(srt_file)

    print(f"Searching for: {args.search}")
    occurrences = find_occurrences(subtitles, args.search)

    if not occurrences:
        print(f"No occurrences found for: {args.search}")
        sys.exit(0)

    print(f"Found {len(occurrences)} occurrence(s)")

    clip_paths = extract_clips(
        input_file, occurrences, args.before, args.after, cuts_dir
    )

    output_file = args.output or os.path.join(workspace, f"{base_name}_extracts.mp4")
    concat_clips(clip_paths, output_file)

    print(f"\nDone!")
    print(f"Cuts saved to: {cuts_dir}")
    print(f"Final video: {output_file}")


if __name__ == "__main__":
    main()
