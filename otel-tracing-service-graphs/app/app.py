import os
import random
import time
from flask import Flask, request
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
import requests

# Configure the tracer
resource = Resource.create(attributes={
    SERVICE_NAME: "trace-demo"
})
trace.set_tracer_provider(TracerProvider(resource=resource))

# Configure the OTLP exporter using environment variables
# OTEL_EXPORTER_OTLP_ENDPOINT will be used automatically
otlp_exporter = OTLPSpanExporter(endpoint="http://alloy:4317/v1/traces", insecure=True)
span_processor = BatchSpanProcessor(span_exporter=otlp_exporter, max_export_batch_size=1)
trace.get_tracer_provider().add_span_processor(span_processor)

# Create a tracer
tracer = trace.get_tracer(__name__)

# Create a Flask application
app = Flask(__name__)

# Instrument Flask
FlaskInstrumentor().instrument_app(app)

# Instrument requests
RequestsInstrumentor().instrument()

@app.route('/')
def home():
    return """
    <h1>OpenTelemetry Demo</h1>
    <p>This app demonstrates OpenTelemetry tracing with Grafana Alloy.</p>
    <ul>
        <li><a href="/simple">Simple Trace</a></li>
        <li><a href="/nested">Nested Trace</a></li>
        <li><a href="/error">Error Trace</a></li>
        <li><a href="/chain">Chain of Services</a></li>
    </ul>
    """

@app.route('/simple')
def simple_trace():
    with tracer.start_as_current_span("simple-operation") as span:
        span.set_attribute("operation.type", "simple")
        span.set_attribute("operation.value", random.randint(1, 100))
        time.sleep(0.1)  # Simulate work
        return {"status": "ok", "message": "Simple trace generated"}

@app.route('/nested')
def nested_trace():
    with tracer.start_as_current_span("parent-operation") as parent:
        parent.set_attribute("operation.type", "parent")
        time.sleep(0.05)  # Simulate work
        
        with tracer.start_as_current_span("child-operation-1") as child1:
            child1.set_attribute("operation.type", "child")
            child1.set_attribute("child.number", 1)
            time.sleep(0.05)  # Simulate work
            
        with tracer.start_as_current_span("child-operation-2") as child2:
            child2.set_attribute("operation.type", "child")
            child2.set_attribute("child.number", 2)
            time.sleep(0.05)  # Simulate work
            
            with tracer.start_as_current_span("grandchild-operation") as grandchild:
                grandchild.set_attribute("operation.type", "grandchild")
                time.sleep(0.05)  # Simulate work
                
        return {"status": "ok", "message": "Nested trace generated"}

@app.route('/error')
def error_trace():
    with tracer.start_as_current_span("error-operation") as span:
        span.set_attribute("operation.type", "error")
        try:
            # Simulate an error
            result = 1 / 0
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            return {"status": "error", "message": "Error trace generated"}

@app.route('/chain')
def chain_trace():
    with tracer.start_as_current_span("chain-root") as span:
        span.set_attribute("operation.step", "start")
        
        # Simulate a chain of service calls
        try:
            # Call ourselves to simulate microservice calls
            # In a real world example these would be different services
            service_b_url = f"http://localhost:8080/service/b?id={random.randint(1000, 9999)}"
            response = requests.get(service_b_url)
            return {"status": "ok", "message": "Chain trace generated", "data": response.json()}
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            return {"status": "error", "message": "Failed to complete chain"}

@app.route('/service/b')
def service_b():
    req_id = request.args.get('id', 'unknown')
    with tracer.start_as_current_span(f"service-b-handler") as span:
        span.set_attribute("service", "B")
        span.set_attribute("request.id", req_id)
        time.sleep(0.1)  # Simulate work
        
        # Call service C
        service_c_url = f"http://localhost:8080/service/c?id={req_id}"
        response = requests.get(service_c_url)
        return {"status": "ok", "message": "Service B completed", "data": response.json()}

@app.route('/service/c')
def service_c():
    req_id = request.args.get('id', 'unknown')
    with tracer.start_as_current_span(f"service-c-handler") as span:
        span.set_attribute("service", "C")
        span.set_attribute("request.id", req_id)
        time.sleep(0.15)  # Simulate work
        
        # Randomly fail sometimes to show error traces
        if random.random() < 0.2:  # 20% chance of failure
            span.set_status(trace.StatusCode.ERROR, "Random failure")
            return {"status": "error", "message": "Service C failed randomly"}
        
        return {"status": "ok", "message": "Service C completed successfully"}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080) 