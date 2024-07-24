from flask import Flask, render_template, request, redirect, url_for, jsonify
import vlc
import schedule
import time
from datetime import datetime
import threading
import logging
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Ensure the upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# VLC player setup
vlc_instance = vlc.Instance()
player = vlc_instance.media_player_new()

# Global variables for scheduling
mute_times = {}
unmute_times = {}
radio_url = ''
is_playing = False  # Track if the radio is playing

# Default schedules
default_mute_times = {
    'monday': ['10:00', '12:00', '14:30', '17:00'],
    'tuesday': ['10:00', '12:00', '14:30', '17:00'],
    'wednesday': ['10:00', '12:00', '14:30', '17:00'],
    'thursday': ['10:00', '12:00', '14:30', '17:00'],
    'friday': ['10:00', '12:00', '14:30', '17:00'],
    'saturday': [],
    'sunday': []
}

default_unmute_times = {
    'monday': ['08:00', '10:15', '12:30', '14:45'],
    'tuesday': ['08:00', '10:15', '12:30', '14:45'],
    'wednesday': ['08:00', '10:15', '12:30', '14:45'],
    'thursday': ['08:00', '10:15', '12:30', '14:45'],
    'friday': ['08:00', '10:15', '12:30', '14:45'],
    'saturday': [],
    'sunday': []
}

def play_radio():
    global is_playing
    media = vlc_instance.media_new(radio_url)
    player.set_media(media)
    logging.info(f"{datetime.now()}: Starting the radio")
    player.play()
    is_playing = True

def stop_radio():
    global is_playing
    logging.info(f"{datetime.now()}: Stopping the radio")
    player.stop()
    is_playing = False

def toggle_radio():
    global is_playing
    if is_playing:
        stop_radio()
    else:
        play_radio()

def ring_alarm():
    alarm_path = os.path.join(os.path.dirname(__file__), 'alarm.mp3')  # Ensure correct relative path
    alarm = vlc_instance.media_new(alarm_path)
    player.set_media(alarm)
    player.play()
    time.sleep(5)  # Ring alarm for 5 seconds
    player.stop()

def mute_radio():
    if player.audio_get_mute() == 0:
        logging.info(f"{datetime.now()}: Muting the radio")
        ring_alarm()
        player.audio_toggle_mute()

def unmute_radio():
    if player.audio_get_mute() == 1:
        logging.info(f"{datetime.now()}: Unmuting the radio")
        player.audio_toggle_mute()

def schedule_tasks():
    schedule.clear()
    logging.info(f"{datetime.now()}: Scheduling tasks")
    for day, times in mute_times.items():
        for mute_time in times:
            if mute_time:  # Ensure the time is not empty
                logging.info(f"Scheduling mute at {mute_time} on {day}")
                getattr(schedule.every(), day.lower()).at(mute_time).do(mute_radio)
    for day, times in unmute_times.items():
        for unmute_time in times:
            if unmute_time:  # Ensure the time is not empty
                logging.info(f"Scheduling unmute at {unmute_time} on {day}")
                getattr(schedule.every(), day.lower()).at(unmute_time).do(unmute_radio)

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

threading.Thread(target=run_schedule, daemon=True).start()

def get_stations():
    conn = sqlite3.connect('stations.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stations')
    stations = cursor.fetchall()
    conn.close()
    return stations

def get_schedules():
    conn = sqlite3.connect('stations.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM schedules')
    schedules = cursor.fetchall()
    conn.close()
    return schedules

@app.route('/', methods=['GET', 'POST'])
def index():
    global radio_url, mute_times, unmute_times
    try:
        if request.method == 'POST':
            radio_url = request.form.get('radio_url')
            station_id = request.form.get('station_id')
            mute_times = {}
            unmute_times = {}
            conn = sqlite3.connect('stations.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM schedules WHERE station_id = ?', (station_id,))
            for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                if day in request.form.getlist('days'):  # Only process selected days
                    mute_times[day] = [time for time in request.form.getlist(f'mute_times_{day}[]') if time]
                    unmute_times[day] = [time for time in request.form.getlist(f'unmute_times_{day}[]') if time]
                    for mute_time, unmute_time in zip(mute_times[day], unmute_times[day]):
                        cursor.execute('INSERT INTO schedules (station_id, day, mute_time, unmute_time) VALUES (?, ?, ?, ?)',
                                       (station_id, day, mute_time, unmute_time))
            conn.commit()
            conn.close()
            logging.info(f"Radio URL: {radio_url}")
            logging.info(f"Mute Times: {mute_times}")
            logging.info(f"Unmute Times: {unmute_times}")
            schedule_tasks()
            return redirect(url_for('index'))
        else:
            # Load default schedules
            mute_times = default_mute_times
            unmute_times = default_unmute_times
            schedule_tasks()
        stations = get_stations()
        schedules = get_schedules()
        return render_template('index.html', radio_url=radio_url, mute_times=mute_times, unmute_times=unmute_times, stations=stations, schedules=schedules)
    except Exception as e:
        logging.error(f"Error processing request: {e}", exc_info=True)
        return "Internal Server Error", 500

@app.route('/add_station', methods=['POST'])
def add_station():
    try:
        name = request.form.get('name')
        url = request.form.get('url')
        image = request.files.get('image')
        
        if image:
            filename = secure_filename(image.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)
        else:
            filename = 'default-station-image.jpg'
        
        conn = sqlite3.connect('stations.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO stations (name, url, image_url) VALUES (?, ?, ?)', (name, url, filename))
        conn.commit()
        conn.close()
        return jsonify({'success': True}), 200
    except Exception as e:
        logging.error(f"Error adding station: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/select_station', methods=['POST'])
def select_station():
    try:
        global radio_url
        data = request.json
        radio_url = data.get('url')
        toggle_radio()
        return jsonify({'success': True}), 200
    except Exception as e:
        logging.error(f"Error selecting station: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == "__main__":
    from waitress import serve
    serve(app, host='0.0.0.0', port=8080)
