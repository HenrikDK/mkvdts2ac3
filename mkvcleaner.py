#!/usr/bin/python

import os
import re
import sys
import subprocess
import time
import shutil
import errno

# change this for other languages (3 character code)
language = "eng"
working_directory = "/folder/to/convert"
audio_codecs = ["TRUEHD", "DTS", "AC3"]

# set this to the path for mkvmerge
mkvmerge = "mkvmerge"

def do_print(message):
    sys.stdout.write(message + "\n")


def silent_remove(filename):
    try:
        os.remove(filename)
    except OSError, e:
        if e.errno != errno.ENOENT: # errno.ENOENT = no such file or directory
            raise


def run_command(command_parameters):
    command_string = ''
    for parameter in command_parameters:
        command_string += parameter + ' '
    print
    print "    Running command:"
    print command_string.rstrip()
    print

    subprocess.call(command_parameters)


def get_elapsed_time(start_time):
    elapsed = (time.time() - start_time)
    minutes = int(elapsed / 60)
    mplural = 's'
    if minutes == 1:
        mplural = ''
    seconds = int(elapsed) % 60
    splural = 's'
    if seconds == 1:
        splural = ''
    return str(minutes) + " minute" + mplural + " " + str(seconds) + " second" + splural


def replace_movie(original_mkv, new_mkv):
    if os.path.exists(new_mkv) and os.path.exists(original_mkv):
        silent_remove(original_mkv)
        shutil.move(new_mkv, original_mkv)


def print_statistics(file_name, start_time):
    #~ print out time taken
    elapsed = (time.time() - start_time)
    minutes = int(elapsed / 60)
    seconds = int(elapsed) % 60
    do_print("  " + file_name + " finished in: " + str(minutes) + " minutes " + str(seconds) + " seconds\n")


def extract_audio_and_subtitle_track_details(movie_structure):
    audio = []
    subtitle = []

    for line in movie_structure.split("\n"):
        track = extract_track_info(line)
        if track["type"] == "audio":
            audio.append(track)
        if track["type"] == "subtitles":
            subtitle.append(track)

    return (audio, subtitle)


def extract_track_info(line):
    track_id = get_track_id(line)
    language = get_language(line)
    default = get_track_default(line)
    type = get_track_type(line)
    codec = get_track_codec(line)
    track = {"track_id":track_id, "type":type, "codec":codec, "language":language, "default":default}
    return track


def get_track_id(line):
    track_id_begin = line.find("Track ID ") + len("Track ID ")
    track_id_end = line.find(":")
    return line[track_id_begin:track_id_end]


def get_language(line):
    language_begin = line.find("language:") + len("language:")
    language_end = language_begin + 3
    return line[language_begin: language_end]


def get_track_type(line):
    type_begin = line.find(": ") + len(": ")
    type_end = line.find(" (")
    return line[type_begin:type_end]


def get_track_default(line):
    if line.find("default_track:") > 0:
        default_begin = line.find("default_track:") + len("default_track:")
        default_end = default_begin + 1
        return int(line[default_begin:default_end])
    return 0


def get_track_codec(line):
    codec_begin = line.find(" (") + len(" (")
    codec_end = line.find(")")
    codec = line[codec_begin:codec_end]
    return codec


def movie_only_has_one_language(audio, subtitle):
    audio_languages = set(a["language"] for a in audio)
    subtitle_languages = set(s["language"] for s in subtitle)
    return len(audio) == 1 and len(audio_languages) == 1 and len(subtitle_languages) == 1


def add_audio_tracks(audio_lang, cmd):
    if len(audio_lang):
        cmd += ["--audio-tracks", ",".join([a["track_id"] for a in audio_lang])]
        for audio_track in audio_lang:
            cmd += ["--default-track", audio_track["track_id"] + ":" + str(audio_track["default"])]
    return cmd


def add_subtitle_tracks(subtitle_lang, cmd):
    if len(subtitle_lang):
        cmd += ["--subtitle-tracks", ",".join([str(s["track_id"]) for s in subtitle_lang])]
        for subtitle_track in subtitle_lang:
            cmd += ["--default-track", subtitle_track["track_id"] + ":" + str(subtitle_track["default"])]
    else:
        cmd += ["--no-subtitles"]
    return cmd


def filter_audio_and_subtitle_languages(audio, subtitle, language):
    audio_lang = filter(lambda a: a["language"] == language, audio)
    subtitle_lang = filter(lambda a: a["language"] == language, subtitle)
    return audio_lang, subtitle_lang


def language_not_in_movie(audio_lang):
    return len(audio_lang) == 0


def select_highest_quality_audio_track(audio_lang):
    for codec in audio_codecs:
        for lang in audio_lang:
            if lang["codec"] == codec:
                audio_lang = [lang]
                break

    return audio_lang


def clean_movie(movie_path):
    if os.path.isdir(movie_path):
        return

    do_print("    Cleaning file: " + movie_path + "\n")

    # check if file is an mkv file
    child = subprocess.Popen([mkvmerge, "--identify-verbose", movie_path], stdout=subprocess.PIPE)
    movie_structure = child.communicate()[0]

    if child.returncode != 0:
        do_print("    Not a valid mkv file, exiting..")
        return

    (audio, subtitle) = extract_audio_and_subtitle_track_details(movie_structure)

    # filter out files that don't need processing
    if movie_only_has_one_language(audio, subtitle):
        do_print("    Nothing to do, " + movie_path + " is already a single language movie. ")
        return

    do_print("    Removing audio and subtitle tracks that don't match our language")
    audio_lang, subtitle_lang = filter_audio_and_subtitle_languages(audio, subtitle, language)

    do_print("    Selecting highest quality audio track:")
    audio_lang = select_highest_quality_audio_track(audio_lang)

    if language_not_in_movie(audio_lang):
        do_print("    Language " + language + " not in movie, exiting..")
        return

    # build command line
    cmd = [mkvmerge, "-o", movie_path + ".temp"]

    do_print("    Adding Audio Track: " + repr(audio_lang))
    cmd = add_audio_tracks(audio_lang, cmd)

    do_print("    Adding Subtitle Tracks: " + repr(subtitle_lang))
    cmd = add_subtitle_tracks(subtitle_lang, cmd)

    cmd += [movie_path]

    do_print("    Remuxing MKV")
    run_command(cmd)

    do_print("    Replacing movie with new file")
    replace_movie(movie_path, movie_path + ".temp")


def process():
    start_time = time.time()
    if os.path.isdir(working_directory):
        for f in os.listdir(working_directory):
            if f.rfind(".mkv") > 0:
                clean_movie(os.path.join(working_directory, f))

    do_print("Total processing time: " + get_elapsed_time(start_time))


if __name__ == "__main__":
    process()