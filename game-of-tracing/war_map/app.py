import os
import json
import sqlite3
import requests
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from telemetry import GameTelemetry
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from opentelemetry.propagate import inject

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'war_of_westeros_secret_key')

# AI Service configuration
AI_SERVICE_URL = os.environ.get('AI_URL', 'http://localhost:8081')

@app.after_request
def remove_frame_options(response):
    response.headers.pop('X-Frame-Options', None)
    return response

# Configuration
DATABASE_FILE = os.environ.get('DATABASE_FILE', '../app/game_state.db')
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost')  # Base URL for API calls

# Initialize telemetry
telemetry = GameTelemetry('war_map')
logger = telemetry.get_logger()
tracer = telemetry.get_tracer()

# Location server ports (from game_config.py)
LOCATION_PORTS = {
    "southern_capital": 5001,
    "northern_capital": 5002,
    "village_1": 5003,
    "village_2": 5004,
    "village_3": 5005,
    "village_4": 5006,
    "village_5": 5007,
    "village_6": 5008
}

# Location positions for the map (x, y coordinates as percentages)
LOCATION_POSITIONS = {
    "southern_capital": {"x": 20, "y": 70, "type": "capital", "name": "Southern Capital"},
    "northern_capital": {"x": 80, "y": 20, "type": "capital", "name": "Northern Capital"},
    "village_1": {"x": 35, "y": 55, "type": "village", "name": "Village 1"},
    "village_2": {"x": 65, "y": 35, "type": "village", "name": "Village 2"},
    "village_3": {"x": 30, "y": 40, "type": "village", "name": "Village 3"},
    "village_4": {"x": 45, "y": 65, "type": "village", "name": "Village 4"},
    "village_5": {"x": 50, "y": 50, "type": "village", "name": "Village 5"},
    "village_6": {"x": 70, "y": 45, "type": "village", "name": "Village 6"}
}

# Location connections for the map (to draw lines between connected locations)
LOCATION_CONNECTIONS = [
    ["southern_capital", "village_1"],
    ["southern_capital", "village_3"],
    ["northern_capital", "village_2"],
    ["northern_capital", "village_6"],
    ["village_1", "village_2"],
    ["village_1", "village_4"],
    ["village_2", "village_5"],
    ["village_3", "village_5"],
    ["village_3", "village_6"],
    ["village_4", "village_5"],
    ["village_5", "village_6"]
]

# Game state - track victory conditions
GAME_OVER = False
WINNER = None
VICTORY_MESSAGE = None

def get_db_connection():
    """Create a connection to the SQLite database"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def check_faction_availability(faction):
    """Check if a faction is already claimed by another player"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if the war_map table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='war_map'")
        if not cursor.fetchone():
            # Create the war_map table if it doesn't exist
            cursor.execute('''
            CREATE TABLE war_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faction TEXT UNIQUE NOT NULL,
                player_name TEXT,
                session_id TEXT UNIQUE
            )
            ''')
            conn.commit()
        
        # Check if the faction is already taken
        cursor.execute("SELECT * FROM war_map WHERE faction = ?", (faction,))
        result = cursor.fetchone()
        
        conn.close()
        logger.info(f"Faction availability check: {result is None}")
        return result is None  # True if available, False if taken
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False

def register_faction(faction, player_name, session_id):
    """Register a player's faction choice"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Try to insert the new faction record
        cursor.execute(
            "INSERT INTO war_map (faction, player_name, session_id) VALUES (?, ?, ?)",
            (faction, player_name, session_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"Faction registered: {faction} for {player_name} with session ID {session_id}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error when registering faction: {e}")
        return False

def get_player_faction(session_id):
    """Get the faction associated with a session ID"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT faction FROM war_map WHERE session_id = ?", (session_id,))
        result = cursor.fetchone()
        
        conn.close()
        logger.info(f"Player faction retrieved: {result['faction'] if result else None}")
        return result['faction'] if result else None
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None

def release_faction(session_id):
    """Release a faction when a player logs out or disconnects"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM war_map WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        logger.info(f"Faction released for session ID: {session_id}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error when releasing faction: {e}")
        return False

def release_all_factions():
    """Release all faction assignments - used for game reset"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM war_map")
        conn.commit()
        conn.close()
        logger.info("All factions released")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error when releasing all factions: {e}")
        return False

def get_location_url(location_id):
    """Get the URL for a location's API"""
    # In Docker, use container names instead of localhost
    if os.environ.get('IN_DOCKER'):
        host = location_id.replace('_', '-')
    else:
        host = 'localhost'
    
    port = LOCATION_PORTS[location_id]
    return f"http://{host}:{port}"

def make_api_request(location_id, endpoint, method='GET', data=None):
    """Make an API request to a location server with trace context."""
    url = f"{get_location_url(location_id)}/{endpoint}"
    
    # Only create spans for important operations, not for status checks
    important_endpoints = {'move_army', 'all_out_attack', 'send_resources_to_capital', 'receive_army', 'receive_resources'}
    
    headers = {"Content-Type": "application/json"}
    if endpoint in important_endpoints:
        # Create span only for important operations
        with tracer.start_as_current_span(
            "location_api_request",
            kind=SpanKind.CLIENT,
            attributes={
                "location.id": location_id,
                "location.endpoint": endpoint,
                "http.method": method
            }
        ) as span:
            inject(headers)  # Inject trace context into headers
            try:
                if method == 'GET':
                    response = requests.get(url, headers=headers)
                else:  # POST
                    response = requests.post(url, json=data, headers=headers)
                
                span.set_attribute("http.status_code", response.status_code)
                response.raise_for_status()
                result = response.json()
                
                if not result.get("success", True):
                    span.set_status(trace.StatusCode.ERROR, result.get("message", "Unknown error"))
                
                return result
            except requests.RequestException as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                return {"error": str(e)}
    else:
        # For status checks and other non-important operations, just make the request without tracing
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            else:  # POST
                response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}

def check_game_over(locations_data):
    """Check if the game is over by examining location ownership"""
    global GAME_OVER, WINNER, VICTORY_MESSAGE
    
    # Check if Southern Capital is owned by Northern
    if locations_data.get('southern_capital', {}).get('faction') == 'northern':
        GAME_OVER = True
        WINNER = 'northern'
        VICTORY_MESSAGE = "The Northern Kingdom has conquered the Southern Capital! Victory through unity!"
        return True
    
    # Check if Northern Capital is owned by Southern
    if locations_data.get('northern_capital', {}).get('faction') == 'southern':
        GAME_OVER = True
        WINNER = 'southern'
        VICTORY_MESSAGE = "The Southern Kingdom has conquered the Northern Capital! Glory to the South!"
        return True
    
    logger.info("Game is not over")
    return False

def reset_game_state():
    """Reset the game state"""
    global GAME_OVER, WINNER, VICTORY_MESSAGE
    GAME_OVER = False
    WINNER = None
    VICTORY_MESSAGE = None

def reset_game_data():
    """Reset the game completely by resetting each location's state"""
    # First, reset our local game state
    reset_game_state()
    
    # Next, reset all faction assignments
    release_all_factions()
    
    # Finally, reset one location to trigger a database reset
    # (Since they all share the same database, we only need to reset one)
    try:
        make_api_request('southern_capital', 'reset', method='POST')
        logger.info("Game data reset")
        return True
    except Exception as e:
        logger.error(f"Error resetting game data: {e}")
        return False

@app.route('/')
def index():
    """Home page - faction selection"""
    # Check if user already has a faction
    if 'session_id' in session and get_player_faction(session['session_id']):
        return redirect(url_for('game_map'))
    
    # Check which factions are available
    southern_available = check_faction_availability('southern')
    northern_available = check_faction_availability('northern')
    logger.info(f"Southern available: {southern_available}, Northern available: {northern_available}")
    
    return render_template('index.html', 
                          southern_available=southern_available, 
                          northern_available=northern_available)

@app.route('/select_faction', methods=['POST'])
def select_faction():
    """Process faction selection"""
    faction = request.form.get('faction')
    player_name = request.form.get('player_name', 'Unknown Player')
    
    if not faction or faction not in ['southern', 'northern']:
        return render_template('index.html', error="Invalid faction selected")
    
    # Check if faction is available
    if not check_faction_availability(faction):
        logger.info(f"Faction {faction} is already taken")
        return render_template('index.html', 
                              error=f"The {faction.capitalize()} faction is already taken")
    
    # Generate a session ID if not present
    if 'session_id' not in session:
        import uuid
        session['session_id'] = str(uuid.uuid4())
    
    # Register the faction
    if register_faction(faction, player_name, session['session_id']):
        session['faction'] = faction
        session['player_name'] = player_name
        logger.info(f"Faction {faction} registered for {player_name} with session ID {session['session_id']}")
        return redirect(url_for('game_map'))
    else:
        logger.error("Failed to register faction")
        return render_template('index.html', 
                              error="Failed to register faction. Please try again.")

@app.route('/logout')
def logout():
    """Log out and release faction"""
    if 'session_id' in session:
        release_faction(session['session_id'])
        logger.info(f"Faction released for session ID: {session['session_id']}")
    # Clear the session
    session.clear()
    return redirect(url_for('index'))

@app.route('/restart-game')
def restart_game():
    """Reset the game and redirect all players to faction selection"""
    # Reset the entire game state
    success = reset_game_data()
    
    # Clear all sessions
    session.clear()
    
    # Redirect to the home page with a message
    return redirect(url_for('index', reset=success))

@app.route('/map')
def game_map():
    """Game map page"""
    # Check if user has selected a faction
    if 'faction' not in session:
        return redirect(url_for('index'))
    
    faction = session['faction']
    player_name = session.get('player_name', 'Unknown Player')
    
    # Get all location data for the map
    locations_data = {}
    for loc_id in LOCATION_POSITIONS.keys():
        data = make_api_request(loc_id, '')
        if 'error' not in data:
            # Combine API data with position data
            locations_data[loc_id] = {
                **LOCATION_POSITIONS[loc_id],
                'faction': data['faction'],
                'resources': data['resources'],
                'army': data['army']
            }
    
    # Check for game over condition
    check_game_over(locations_data)
    
    return render_template('map.html', 
                          player_name=player_name,
                          faction=faction,
                          locations=locations_data,
                          connections=LOCATION_CONNECTIONS,
                          game_over=GAME_OVER,
                          winner=WINNER,
                          victory_message=VICTORY_MESSAGE)

@app.route('/api/collect_resources', methods=['POST'])
def collect_resources():
    """API endpoint to collect resources at a location"""
    location_id = request.json.get('location_id')
    if not location_id:
        logger.error("Location ID required")
        return jsonify({"error": "Location ID required"}), 400
    
    result = make_api_request(location_id, 'collect_resources', method='POST')
    logger.info(f"Collect resources result: {result}")
    return jsonify(result)

@app.route('/api/create_army', methods=['POST'])
def create_army():
    """API endpoint to create an army at a location"""
    location_id = request.json.get('location_id')
    if not location_id:
        logger.error("Location ID required")
        return jsonify({"error": "Location ID required"}), 400
    
    result = make_api_request(location_id, 'create_army', method='POST')
    logger.info(f"Create army result: {result}")
    return jsonify(result)

@app.route('/api/move_army', methods=['POST'])
def move_army():
    """API endpoint to move an army"""
    with tracer.start_as_current_span(
        "move_army",
        kind=SpanKind.SERVER,
        attributes={
            "player.name": session.get('player_name', 'Unknown'),
            "player.faction": session.get('faction', 'Unknown')
        }
    ) as span:
        source_id = request.json.get('source_id')
        target_id = request.json.get('target_id')
        
        if not source_id or not target_id:
            span.set_status(trace.StatusCode.ERROR, "Missing location IDs")
            return jsonify({"error": "Source and target location IDs required"}), 400
        
        span.set_attribute("source_location", source_id)
        span.set_attribute("target_location", target_id)
        
        # Check if the player controls the source location
        source_info = make_api_request(source_id, '')
        player_faction = session.get('faction')
        
        if source_info.get('faction') != player_faction:
            span.set_status(trace.StatusCode.ERROR, "Not player's location")
            return jsonify({
                "error": f"You cannot move armies from {source_id} because it belongs to {source_info.get('faction')}"
            }), 403
        
        result = make_api_request(
            source_id, 
            'move_army', 
            method='POST',
            data={"target_location": target_id}
        )
        
        # Check if this move resulted in a victory condition
        if target_id in ['southern_capital', 'northern_capital'] and result.get('success'):
            locations_data = {}
            for loc_id in LOCATION_POSITIONS.keys():
                data = make_api_request(loc_id, '')
                if 'error' not in data:
                    locations_data[loc_id] = {
                        'faction': data['faction']
                    }
            
            if check_game_over(locations_data):
                result['game_over'] = True
                result['winner'] = WINNER
                result['victory_message'] = VICTORY_MESSAGE
                span.set_attribute("game_over", True)
                span.set_attribute("winner", WINNER)
        
        return jsonify(result)

@app.route('/api/location_info/<location_id>', methods=['GET'])
def location_info(location_id):
    """API endpoint to get information about a location"""
    if location_id not in LOCATION_POSITIONS:
        return jsonify({"error": "Invalid location ID"}), 400
    
    result = make_api_request(location_id, '')
    logger.info(f"Location info result: {result}")
    return jsonify(result)

@app.route('/api/map_data', methods=['GET'])
def map_data():
    """API endpoint to get all map data for updating the UI"""
    # Get all location data for the map
    locations_data = {}
    for loc_id in LOCATION_POSITIONS.keys():
        data = make_api_request(loc_id, '')
        if 'error' not in data:
            # Combine API data with position data and location type
            locations_data[loc_id] = {
                **LOCATION_POSITIONS[loc_id],
                'faction': data['faction'],
                'resources': data['resources'],
                'army': data['army'],
                'type': LOCATION_POSITIONS[loc_id]['type']  # Add location type
            }
    
    # Check for game over condition
    check_game_over(locations_data)
    
    return jsonify({
        "locations": locations_data,
        "connections": LOCATION_CONNECTIONS,
        "game_over": GAME_OVER,
        "winner": WINNER,
        "victory_message": VICTORY_MESSAGE
    })

@app.route('/api/game_status', methods=['GET'])
def game_status():
    """API endpoint to get the current game status"""
    # Always check the current state to catch AI victories
    locations_data = {}
    for loc_id in LOCATION_POSITIONS.keys():
        data = make_api_request(loc_id, '')
        if 'error' not in data:
            locations_data[loc_id] = {
                'faction': data['faction']
            }
    
    # Check for game over condition with fresh data
    check_game_over(locations_data)
    
    return jsonify({
        "game_over": GAME_OVER,
        "winner": WINNER,
        "victory_message": VICTORY_MESSAGE
    })

@app.route('/api/reset_game', methods=['POST'])
def reset_game():
    """Reset the game state (for testing)"""
    success = reset_game_data()
    return jsonify({"success": success, "message": "Game has been reset"})

@app.route('/api/send_resources_to_capital', methods=['POST'])
def send_resources_to_capital():
    """API endpoint to send resources from a village to its capital"""
    with tracer.start_as_current_span(
        "send_resources_to_capital",
        kind=SpanKind.SERVER,
        attributes={
            "player.name": session.get('player_name', 'Unknown'),
            "player.faction": session.get('faction', 'Unknown')
        }
    ) as span:
        location_id = request.json.get('location_id')
        if not location_id:
            span.set_status(trace.StatusCode.ERROR, "Missing location ID")
            return jsonify({"error": "Location ID required"}), 400
        
        span.set_attribute("source_location", location_id)
        
        # Forward the request to the location server
        result = make_api_request(location_id, 'send_resources_to_capital', method='POST')
        return jsonify(result)

@app.route('/api/all_out_attack', methods=['POST'])
def all_out_attack():
    """API endpoint to launch an all-out attack from a capital"""
    with tracer.start_as_current_span(
        "all_out_attack",
        kind=SpanKind.SERVER,
        attributes={
            "player.name": session.get('player_name', 'Unknown'),
            "player.faction": session.get('faction', 'Unknown')
        }
    ) as span:
        location_id = request.json.get('location_id')
        if not location_id:
            span.set_status(trace.StatusCode.ERROR, "Missing location ID")
            return jsonify({"success": False, "message": "Location ID required"}), 400
        
        span.set_attribute("source_location", location_id)
        
        # Check if the player controls the source location
        source_info = make_api_request(location_id, '')
        if 'error' in source_info:
            span.set_status(trace.StatusCode.ERROR, f"Error getting location info: {source_info['error']}")
            return jsonify({"success": False, "message": f"Error getting location info: {source_info['error']}"}), 500
            
        player_faction = session.get('faction')
        
        if source_info.get('faction') != player_faction:
            span.set_status(trace.StatusCode.ERROR, "Not player's location")
            return jsonify({
                "success": False,
                "message": f"You cannot launch attack from {location_id} because it belongs to {source_info.get('faction')}"
            }), 403
        
        # Forward the request to the location server
        try:
            result = make_api_request(location_id, 'all_out_attack', method='POST', data=request.json)
            if 'error' in result:
                span.set_status(trace.StatusCode.ERROR, f"Error from location server: {result['error']}")
                return jsonify({"success": False, "message": f"Error from location server: {result['error']}"}), 500
            
            # Check if this attack resulted in game over
            if result.get('success'):
                locations_data = {}
                for loc_id in LOCATION_POSITIONS.keys():
                    data = make_api_request(loc_id, '')
                    if 'error' not in data:
                        locations_data[loc_id] = {
                            'faction': data['faction']
                        }
                
                if check_game_over(locations_data):
                    result['game_over'] = True
                    result['winner'] = WINNER
                    result['victory_message'] = VICTORY_MESSAGE
                    span.set_attribute("game_over", True)
                    span.set_attribute("winner", WINNER)
            
            return jsonify(result)
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            return jsonify({"success": False, "message": f"Failed to launch attack: {str(e)}"}), 500

@app.route('/api/ai_toggle', methods=['POST'])
def toggle_ai():
    """Toggle AI opponent on/off"""
    data = request.get_json()
    enable_ai = data.get('enable', False)
    
    if enable_ai:
        # Get player's faction to determine AI faction
        player_faction = session.get('faction')
        if not player_faction:
            return jsonify({"success": False, "message": "No player faction selected"}), 400
        
        # AI takes the opposite faction
        ai_faction = 'northern' if player_faction == 'southern' else 'southern'
        
        # Activate AI
        try:
            response = requests.post(
                f"{AI_SERVICE_URL}/activate",
                json={"faction": ai_faction},
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    logger.info(f"AI activated for {ai_faction} faction")
                    return jsonify({
                        "success": True,
                        "message": f"AI opponent activated for {ai_faction} faction"
                    })
            
            return jsonify({
                "success": False,
                "message": "Failed to activate AI"
            }), 500
            
        except requests.RequestException as e:
            logger.error(f"Error communicating with AI service: {e}")
            return jsonify({
                "success": False,
                "message": "AI service unavailable"
            }), 503
    else:
        # Deactivate AI
        try:
            response = requests.post(
                f"{AI_SERVICE_URL}/deactivate",
                timeout=5
            )
            if response.status_code == 200:
                logger.info("AI deactivated")
                return jsonify({
                    "success": True,
                    "message": "AI opponent deactivated"
                })
            
            return jsonify({
                "success": False,
                "message": "Failed to deactivate AI"
            }), 500
            
        except requests.RequestException as e:
            logger.error(f"Error communicating with AI service: {e}")
            return jsonify({
                "success": False,
                "message": "AI service unavailable"
            }), 503

@app.route('/api/ai_status', methods=['GET'])
def get_ai_status():
    """Get current AI status"""
    try:
        response = requests.get(f"{AI_SERVICE_URL}/status", timeout=5)
        if response.status_code == 200:
            return jsonify(response.json())
        
        return jsonify({"active": False, "faction": None})
    except requests.RequestException:
        return jsonify({"active": False, "faction": None})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True) 