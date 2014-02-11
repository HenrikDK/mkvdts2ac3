#!/usr/bin/python

import argparse
import os
import subprocess
import time
import re
import sys
import shutil
import textwrap
import errno

#set global variables
test = True
working_directory = "/volume1/Data/download/convert/"
temp_working_directory = working_directory + "/tmp"
language = "eng"
audio_codecs = ["A_TRUEHD", "A_DTS"]

# set ffmpeg and mkvtoolnix paths
mkvinfo = "mkvinfo"
mkvmerge = "mkvmerge"
mkvextract = "mkvextract"
ffmpeg = "/usr/local/bin/ffmpeg"

def doprint(message):
    sys.stdout.write(message + "\n")

def silent_remove(filename):
    try:
        os.remove(filename)
    except OSError, e:
        if e.errno != errno.ENOENT: # errno.ENOENT = no such file or directory
            raise # re-raise exception if a different error occured

def elapsedstr(starttime):
    elapsed = (time.time() - starttime)
    minutes = int(elapsed / 60)
    mplural = 's'
    if minutes == 1:
        mplural = ''
    seconds = int(elapsed) % 60
    splural = 's'
    if seconds == 1:
        splural = ''
    return str(minutes) + " minute" + mplural + " " + str(seconds) + " second" + splural

def getduration(time):
    (hms, ms) = time.split('.')
    (h, m, s) = hms.split(':')
    totalms = int(ms) + (int(s) * 100) + (int(m) * 100 * 60) + (int(h) * 100 * 60 * 60)
    return totalms
   
def runcommand( title, cmdlist):
    if test:
        cmdstr = ''
        for e in cmdlist:
            cmdstr += e + ' '
        print
        print "    Running command:"
        print textwrap.fill(cmdstr.rstrip(), initial_indent='      ', subsequent_indent='      ')
    else:
        subprocess.call(cmdlist, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def find_mount_point(path):
    path = os.path.abspath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def clean_up_temp_folder(tempac3file, tempdtsfile, temptcfile):
    if not test:
        silent_remove(tempdtsfile)
        silent_remove(tempac3file)
        silent_remove(temptcfile)


def print_statistics(fileName, starttime):
    #~ print out time taken
    elapsed = (time.time() - starttime)
    minutes = int(elapsed / 60)
    seconds = int(elapsed) % 60
    doprint("  " + fileName + " finished in: " + str(minutes) + " minutes " + str(seconds) + " seconds\n")

def remux_movie(movie_path, audio_track_name, audio_delay, audio_language, tempac3file, tempmkvfile, video_track_id):
    # remux
    remux = [mkvmerge]

    # always drop all other audio tracks
    remux.append("-A")

    # Add original MKV file, set header compression scheme
    remux.append("--compression")
    remux.append(video_track_id + ":none")
    remux.append(movie_path)

    # Set the language
    remux.append("--language")
    remux.append("0:" + audio_language)

    # If the name was set for the original DTS track set it for the AC3
    if audio_track_name:
        remux.append("--track-name")
        remux.append("0:\"" + audio_track_name.rstrip() + "\"")

    # set delay if there is any
    if audio_delay:
        remux.append("--sync")
        remux.append("0:" + audio_delay.rstrip())

    # Set track compression scheme and append new AC3
    remux.append("--compression")
    remux.append("0:none")
    remux.append(tempac3file)
    # Declare output file
    remux.append("-o")
    remux.append(tempmkvfile)
    runcommand(remux)


def extract_audio(movie_path, main_audio_track, temp_audio_file):
    # extract dts track
    extractcmd = [mkvextract, "tracks", movie_path, main_audio_track + ':' + temp_audio_file]
    runcommand(extractcmd)

def convert_audio(source_audio_file, temp_audio_file):
    # convert Audio
    audiochannels = 6
    convertcmd = [ffmpeg, "-y", "-i", source_audio_file, "-acodec", "ac3", "-ac", str(audiochannels), "-ab", "640k", temp_audio_file]
    runcommand(convertcmd)

def calculate_audio_delay(movie_path, dtstrackid, temptcfile):
    tccmd = [mkvextract, "timecodes_v2", movie_path, dtstrackid + ":" + temptcfile]
    runcommand(tccmd)

    delay = False
    if not test:
        # get the delay if there is any
        fp = open(temptcfile)
        for i, line in enumerate(fp):
            if i == 1:
                delay = line
                break
        fp.close()
    return delay


def replace_movie(original_mkv, new_mkv):
    if not test:
        silent_remove(original_mkv)
        shutil.move(new_mkv, original_mkv)


def get_track_id(line):
    linelist = line.split(' ')
    trackid = False
    if len(linelist) > 2:
        trackid = linelist[2]
        linelist = trackid.split(':')
        trackid = linelist[0]
    return trackid


def extract_general_track_info(movie_path):
    # get main track id and video track id
    output = subprocess.check_output([mkvmerge, "-i", movie_path])
    lines = output.split("\n")

    video_track_id = False
    audio_tracks = []
    for line in lines:
        trackid = get_track_id(line)
        if 'audio (A_' in line:
            audio_tracks.append(line)
        elif 'video (V_' in line:
            video_track_id = trackid

    return video_track_id, audio_tracks


def parse_mkvinfo_output(lines, main_audio_track):
    movie_track_info = []
    startcount = 0
    for line in lines:
        match = re.search(r'^\|( *)\+', line)
        linespaces = startcount
        if match:
            linespaces = len(match.group(1))
        if startcount == 0:
            if "track ID for mkvmerge & mkvextract:" in line:
                if "track ID for mkvmerge & mkvextract: " + main_audio_track in line:
                    startcount = linespaces
            elif "+ Track number: " + main_audio_track in line:
                startcount = linespaces
        if linespaces < startcount:
            break
        if startcount != 0:
            movie_track_info.append(line)
    return movie_track_info


def extract_audio_info(movie_path, main_audio_track):
    output = subprocess.check_output([mkvinfo, movie_path])
    lines = output.split("\n")
    audio_track_info = parse_mkvinfo_output(lines, main_audio_track)

    audio_language = get_main_audio_language(audio_track_info)
    audio_track_name = get_audio_track_name(audio_track_info)

    return audio_language, audio_track_name


def get_audio_track_name(movie_track_info):
    audio_track_name = False
    for track in movie_track_info:
        if "+ Name: " in track:
            audio_track_name = track.split("+ Name: ")[-1]
            audio_track_name = audio_track_name.replace("DTS", "AC3")
            audio_track_name = audio_track_name.replace("dts", "ac3")
            audio_track_name = audio_track_name.replace("TrueHD", "AC3")
            audio_track_name = audio_track_name.replace("truehd", "ac3")
    return audio_track_name


def get_main_audio_language(movie_track_info):
    audio_language = "eng"
    for track in movie_track_info:
        if "Language" in track:
            audio_language = track.split()[-1]
    return audio_language


def check_if_file_has_ac3(audio_tracks):
    already_got_ac3 = False

    for track in audio_tracks:
        if ": audio (A_AC3)" in track:
            already_got_ac3 = True

    return already_got_ac3


def get_main_audio_track(audio_tracks):
    audio_type = ""
    main_audio_track_id = ""

    for track in audio_tracks:
        if audio_codecs[0] in track:
            audio_type = '.thd'
            main_audio_track_id = get_track_id(track)
            break
        if audio_codecs[1] in track:
            audio_type = ".dts"
            main_audio_track_id = get_track_id(track)
            break

    return audio_type, main_audio_track_id


def process_movie(movie_path):
    if os.path.isdir(movie_path):
        return

    starttime = time.time()
    doprint("    Processing file: " + movie_path + "\n")

    # check if file is an mkv file
    child = subprocess.Popen([mkvmerge, "-i", movie_path], stdout=subprocess.PIPE)
    child.communicate()[0]
    if child.returncode != 0:
        return

    (dirName, fileName) = os.path.split(movie_path)
    fileBaseName = os.path.splitext(fileName)[0]

    doprint("filename: " + fileName)

    tempac3file = os.path.join(temp_working_directory, fileBaseName + '.ac3')
    temptcfile = os.path.join(temp_working_directory, fileBaseName + '.tc')
    new_mkv_file = os.path.join(temp_working_directory, fileBaseName + '.new.mkv')

    video_track_id, audio_tracks = extract_general_track_info(movie_path)

    already_got_ac3 = check_if_file_has_ac3(audio_tracks)
    audio_type, main_audio_track_id = get_main_audio_track(audio_tracks)

    main_audio_file = os.path.join(temp_working_directory, fileBaseName + audio_type)

    if already_got_ac3:
        doprint("  Already has AC3 track\n")
        return

    if not main_audio_track_id:
        doprint("  No DTS or TrueHD track found\n")
        return

    doprint("  Extracting audio track information [1/7]...")
    audio_language, audio_track_name  = extract_audio_info(movie_path, main_audio_track_id)

    doprint("  Calculating audio/video delay  [2/7]...")
    delay = calculate_audio_delay(movie_path, main_audio_track_id, temptcfile)

    doprint("  Extracting main Audio track  [3/7]...")
    extract_audio(movie_path, main_audio_track_id, main_audio_file)

    doprint("  Converting audio to AC3  [4/7]...")
    convert_audio(main_audio_file, tempac3file)

    doprint("  Remuxing AC3 into MKV  [5/7]...")
    remux_movie(movie_path, audio_track_name, delay, audio_language, tempac3file, new_mkv_file, video_track_id)

    doprint("  Replacing MKV with new File  [6/7]...")
    replace_movie(movie_path, new_mkv_file)

    doprint("  Deleting temporary files  [7/7]...")
    clean_up_temp_folder(tempac3file, main_audio_file, temptcfile)

    print_statistics(fileName, starttime)
            
def process():
    totalstime = time.time()
    if os.path.isdir(working_directory):
        for f in os.listdir(working_directory):
            if f.rfind(".mkv") > 0:
                process_movie(os.path.join(working_directory, f))

    doprint("Total processing time: " + elapsedstr(totalstime))

if __name__ == "__main__":
    process()