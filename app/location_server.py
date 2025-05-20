import os, sqlite3, requests, random, time, threading
from threading import Thread, Lock
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from game_config import LOCATIONS, COSTS, RESOURCE_GENERATION, DATABASE_FILE
from telemetry import GameTelemetry
from opentelemetry.propagate import extract, inject
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from opentelemetry.context import Context, attach, detach

class LocationServer:
    def __init__(self, location_id):
        self.location_id = location_id
        self.location_info = LOCATIONS[location_id]
        self.app = Flask(__name__)
        self.last_resource_collection = {}
        self.resource_cooldown = {}
        self.lock = Lock()
        
        # Initialize telemetry
        location_name = os.environ.get('LOCATION_NAME', location_id)
        self.telemetry = GameTelemetry(service_name=location_name)
        self.logger = self.telemetry.get_logger()
        self.tracer = self.telemetry.get_tracer()

    def _make_request_with_trace(self, method, url, json_data=None, parent_context: Context = None):
        """Make HTTP request with trace context propagated in headers."""
        # Create headers dictionary to inject trace context into
        headers = {"Content-Type": "application/json"}
        
        # If parent_context is provided, use it, otherwise use current context
        context_to_inject = parent_context or trace.get_current_span().get_span_context()
        
        # Inject the trace context into headers
        inject(headers, context=context_to_inject)
        
        # Make the request with the trace context headers
        try:
            if method.lower() == 'get':
                response = requests.get(url, headers=headers)
            elif method.lower() == 'post':
                response = requests.post(url, json=json_data, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Request failed: {str(e)}")
            raise

    def setup_routes(self):
        """Setup Flask routes for this location"""
        @self.app.route('/all_out_attack', methods=['POST'])
        def all_out_attack():
            """Launch an all-out attack on the enemy capital"""
            # Extract trace context from incoming request
            context = extract(request.headers)
            
            with self.tracer.start_as_current_span(
                "all_out_attack",
                context=context,
                kind=SpanKind.SERVER,
                attributes={
                    "service.name": self.location_info["name"],
                    "location_type": self.location_info["type"]
                }
            ) as attack_span:
                try:
                    # ... existing attack logic ...
                    
                    # If we're not at the end of the path, start movement in background
                    if len(remaining_path) > 1:
                        current_loc = remaining_path[0]
                        next_loc = remaining_path[1]
                        
                        # Capture the current context for the background thread
                        parent_context = trace.get_current_span().get_span_context()
                        
                        def continue_attack():
                            # Start a new span in the background thread with the parent context
                            with self.tracer.start_as_current_span(
                                "army_movement",
                                context=parent_context,
                                kind=SpanKind.CLIENT,
                                attributes={
                                    "source_location": current_loc,
                                    "target_location": next_loc,
                                    "army_size": army_size
                                }
                            ) as movement_span:
                                try:
                                    time.sleep(5)
                                    target_url = f"{self.get_location_url(next_loc)}/receive_army"
                                    
                                    # Pass the current span context to the request
                                    result = self._make_request_with_trace(
                                        'post',
                                        target_url,
                                        {
                                            "army_size": army_size,
                                            "faction": faction,
                                            "source_location": current_loc,
                                            "remaining_path": remaining_path[1:],
                                            "is_attack_move": True
                                        },
                                        parent_context=movement_span.get_span_context()
                                    )
                                    
                                    if not result.get("success", False):
                                        movement_span.set_status(trace.StatusCode.ERROR, "Attack failed")
                                        movement_span.set_attribute("error", result.get("message", "Unknown error"))
                                    
                                except Exception as e:
                                    movement_span.record_exception(e)
                                    movement_span.set_status(trace.StatusCode.ERROR, str(e))
                                    self.logger.error(f"Failed to send army to {next_loc}: {str(e)}")
                        
                        Thread(target=continue_attack).start()
                    
                    return jsonify({
                        "success": True,
                        "message": f"Army of {army_size} continuing attack",
                        "path": remaining_path,
                        "army_size": army_size
                    })
                    
                except Exception as e:
                    attack_span.record_exception(e)
                    attack_span.set_status(trace.StatusCode.ERROR, str(e))
                    raise

        @self.app.route('/receive_army', methods=['POST'])
        def receive_army():
            """Receive an army from another location and resolve any battles"""
            # Extract trace context from incoming request
            context = extract(request.headers)
            
            with self.tracer.start_as_current_span(
                "receive_army",
                context=context,
                kind=SpanKind.SERVER,
                attributes={
                    "service.name": self.location_info["name"],
                    "location_type": self.location_info["type"]
                }
            ) as battle_span:
                try:
                    # ... existing battle logic ...
                    
                    # If continuing movement, capture current context for background thread
                    if is_attack_move and remaining_path:
                        parent_context = trace.get_current_span().get_span_context()
                        
                        def continue_attack():
                            with self.tracer.start_as_current_span(
                                "army_movement",
                                context=parent_context,
                                kind=SpanKind.CLIENT,
                                attributes={
                                    "source_location": self.location_id,
                                    "target_location": remaining_path[0],
                                    "army_size": remaining_army
                                }
                            ) as movement_span:
                                try:
                                    time.sleep(5)
                                    target_url = f"{self.get_location_url(remaining_path[0])}/receive_army"
                                    
                                    result = self._make_request_with_trace(
                                        'post',
                                        target_url,
                                        {
                                            "army_size": remaining_army,
                                            "faction": attacking_faction,
                                            "source_location": self.location_id,
                                            "remaining_path": remaining_path[1:],
                                            "is_attack_move": True
                                        },
                                        parent_context=movement_span.get_span_context()
                                    )
                                    
                                    if not result.get("success", False):
                                        movement_span.set_status(trace.StatusCode.ERROR, "Movement failed")
                                        movement_span.set_attribute("error", result.get("message", "Unknown error"))
                                        
                                except Exception as e:
                                    movement_span.record_exception(e)
                                    movement_span.set_status(trace.StatusCode.ERROR, str(e))
                                    self.logger.error(f"Error continuing attack: {str(e)}")
                        
                        Thread(target=continue_attack).start()
                    
                    return jsonify({
                        "success": battle_result == "attacker_victory",
                        "message": f"Battle at {self.location_info['name']}: {battle_result}",
                        "current_army": remaining_army if 'remaining_army' in locals() else 0,
                        "faction": attacking_faction if battle_result == "attacker_victory" else defending_faction
                    })
                    
                except Exception as e:
                    battle_span.record_exception(e)
                    battle_span.set_status(trace.StatusCode.ERROR, str(e))
                    raise

        @self.app.route('/send_resources_to_capital', methods=['POST'])
        def send_resources_to_capital():
            """Send accumulated resources back to the capital"""
            # Extract trace context from incoming request
            context = extract(request.headers)
            
            with self.tracer.start_as_current_span(
                "send_resources_to_capital",
                context=context,
                kind=SpanKind.SERVER,
                attributes={
                    "service.name": self.location_info["name"],
                    "location_type": self.location_info["type"]
                }
            ) as resource_span:
                try:
                    location_state = self._get_location_state(self.location_id)
                    current_resources = location_state["resources"]
                    faction = location_state["faction"]
                    
                    resource_span.set_attribute("resources_amount", current_resources)
                    resource_span.set_attribute("faction", faction)
                    
                    # Only villages can send resources
                    if self.location_info["type"] != "village":
                        resource_span.set_status(trace.StatusCode.ERROR, "Only villages can send resources")
                        return jsonify({
                            "success": False,
                            "message": "Only villages can send resources to capital"
                        }), 403
                    
                    # Must belong to a faction
                    if faction not in ['lannister', 'stark']:
                        resource_span.set_status(trace.StatusCode.ERROR, "Village must belong to a faction")
                        return jsonify({
                            "success": False,
                            "message": "Village must belong to a faction to send resources"
                        }), 403
                    
                    # Find path to capital
                    path = self._find_path_to_capital(faction)
                    if not path:
                        resource_span.set_status(trace.StatusCode.ERROR, "No valid path to capital")
                        return jsonify({
                            "success": False,
                            "message": "No valid path to capital found"
                        }), 400
                    
                    resource_span.set_attribute("path_to_capital", str(path))
                    
                    # Start resource transfer in background thread
                    if len(path) > 1:
                        current_loc = path[0]
                        next_loc = path[1]
                        
                        # Capture current context for background thread
                        parent_context = trace.get_current_span().get_span_context()
                        
                        def transfer():
                            with self.tracer.start_as_current_span(
                                "resource_movement",
                                context=parent_context,
                                kind=SpanKind.CLIENT,
                                attributes={
                                    "source_location": current_loc,
                                    "target_location": next_loc,
                                    "resources_amount": current_resources
                                }
                            ) as movement_span:
                                try:
                                    time.sleep(5)
                                    target_url = f"{self.get_location_url(next_loc)}/receive_resources"
                                    
                                    result = self._make_request_with_trace(
                                        'post',
                                        target_url,
                                        {
                                            "resources": current_resources,
                                            "source_location": current_loc,
                                            "remaining_path": path[1:],
                                            "faction": faction
                                        },
                                        parent_context=movement_span.get_span_context()
                                    )
                                    
                                    # Deduct resources after successful transfer
                                    if result.get("success", False):
                                        current_loc_resources = self._get_location_state(current_loc)['resources']
                                        self._update_location_state(current_loc, resources=current_loc_resources - current_resources)
                                    else:
                                        movement_span.set_status(trace.StatusCode.ERROR, "Resource transfer failed")
                                        movement_span.set_attribute("error", result.get("message", "Unknown error"))
                                    
                                except Exception as e:
                                    movement_span.record_exception(e)
                                    movement_span.set_status(trace.StatusCode.ERROR, str(e))
                                    self.logger.error(f"Failed to send resources to {next_loc}: {str(e)}")
                        
                        Thread(target=transfer).start()
                        self._start_resource_cooldown()
                        
                        return jsonify({
                            "success": True,
                            "message": f"Sending {current_resources} resources to capital via {' -> '.join(path)}",
                            "path": path,
                            "amount": current_resources
                        })
                    else:
                        resource_span.set_status(trace.StatusCode.ERROR, "Invalid path length")
                        return jsonify({
                            "success": False,
                            "message": "Invalid path to capital"
                        }), 400
                        
                except Exception as e:
                    resource_span.record_exception(e)
                    resource_span.set_status(trace.StatusCode.ERROR, str(e))
                    raise

        @self.app.route('/receive_resources', methods=['POST'])
        def receive_resources():
            """Receive resources from another location and continue transfer if needed"""
            data = request.get_json()
            if not data or 'resources' not in data or 'faction' not in data:
                return jsonify({"success": False, "message": "Invalid resource data"}), 400
            
            # Extract trace context from incoming request
            context = extract(request.headers)
            
            with self.tracer.start_as_current_span(
                "receive_resources",
                context=context,
                kind=SpanKind.SERVER,
                attributes={
                    "service.name": self.location_info["name"],
                    "location_type": self.location_info["type"],
                    "resources_amount": data['resources']
                }
            ) as transfer_span:
                try:
                    incoming_resources = data['resources']
                    source_location = data.get('source_location', 'unknown')
                    remaining_path = data.get('remaining_path', [])
                    faction = data['faction']
                    
                    transfer_span.set_attribute("source_location", source_location)
                    
                    # Get current state
                    location_state = self._get_location_state(self.location_id)
                    current_resources = location_state["resources"]
                    current_faction = location_state["faction"]
                    
                    # Only accept resources if we're the same faction
                    if current_faction != faction:
                        transfer_span.set_status(trace.StatusCode.ERROR, f"Resources captured by {current_faction}")
                        # Resources are captured - just add them to current location
                        self._update_location_state(self.location_id, resources=current_resources + incoming_resources)
                        return jsonify({
                            "success": False,
                            "message": f"Resources captured by {current_faction}!",
                            "current_resources": current_resources + incoming_resources
                        })
                    
                    # Add resources to current location
                    new_resources = current_resources + incoming_resources
                    self._update_location_state(self.location_id, resources=new_resources)
                    
                    # If there are more locations in the path, continue the transfer
                    if len(remaining_path) > 1:
                        next_loc = remaining_path[1]
                        
                        # Capture current context for background thread
                        parent_context = trace.get_current_span().get_span_context()
                        
                        def continue_transfer():
                            with self.tracer.start_as_current_span(
                                "resource_movement",
                                context=parent_context,
                                kind=SpanKind.CLIENT,
                                attributes={
                                    "source_location": self.location_id,
                                    "target_location": next_loc,
                                    "resources_amount": incoming_resources
                                }
                            ) as movement_span:
                                try:
                                    time.sleep(5)
                                    target_url = f"{self.get_location_url(next_loc)}/receive_resources"
                                    
                                    result = self._make_request_with_trace(
                                        'post',
                                        target_url,
                                        {
                                            "resources": incoming_resources,
                                            "source_location": self.location_id,
                                            "remaining_path": remaining_path[1:],
                                            "faction": faction
                                        },
                                        parent_context=movement_span.get_span_context()
                                    )
                                    
                                    if not result.get("success", False):
                                        movement_span.set_status(trace.StatusCode.ERROR, "Resource transfer failed")
                                        movement_span.set_attribute("error", result.get("message", "Unknown error"))
                                    else:
                                        # Deduct resources after successful forward
                                        current_state = self._get_location_state(self.location_id)
                                        self._update_location_state(self.location_id, 
                                            resources=current_state["resources"] - incoming_resources)
                                        
                                except Exception as e:
                                    movement_span.record_exception(e)
                                    movement_span.set_status(trace.StatusCode.ERROR, str(e))
                                    self.logger.error(f"Failed to forward resources to {next_loc}: {str(e)}")
                        
                        Thread(target=continue_transfer).start()
                    
                    transfer_span.set_attribute("final_resources", new_resources)
                    if self.location_info["type"] == "capital":
                        transfer_span.set_attribute("resources_reached_capital", True)
                    
                    return jsonify({
                        "success": True,
                        "message": f"Resources received at {self.location_info['name']}",
                        "current_resources": new_resources
                    })
                    
                except Exception as e:
                    transfer_span.record_exception(e)
                    transfer_span.set_status(trace.StatusCode.ERROR, str(e))
                    raise 