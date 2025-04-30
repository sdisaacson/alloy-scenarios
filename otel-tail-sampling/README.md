# OpenTelemetry Tail Sampling with Grafana Alloy

This example demonstrates how to implement tail sampling for OpenTelemetry traces using Grafana Alloy, allowing you to intelligently filter and sample traces based on various criteria.

## Overview

The example includes:

- A Python Flask application that automatically generates different types of traces in the background
- Grafana Alloy configured with tail sampling policies and transform processor
- Tempo for trace storage and querying
- Prometheus for metrics collection
- Grafana for visualization
- Live debugging for monitoring the sampling process

## Running the Demo

1. Clone the repository:
   ```
   git clone https://github.com/grafana/alloy-scenarios.git
   cd alloy-scenarios
   ```

2. Navigate to this example directory:
   ```
   cd otel-tail-sampling
   ```

3. Run using Docker Compose:
   ```
   docker compose up -d
   ```
   
   Or use the centralized image management:
   ```
   cd ..
   ./run-example.sh otel-tail-sampling
   ```

4. Access the demo application at http://localhost:8080
5. Access Grafana at http://localhost:3000
6. Access Prometheus at http://localhost:9090
7. Access Alloy's live debugging endpoint at http://localhost:12345/debug/livedebugging

## What to Expect

The demo application automatically generates various types of traces in the background:

- **Simple Traces**: Basic single-span traces
- **Nested Traces**: Traces with parent-child relationships
- **Error Traces**: Traces containing errors
- **High Latency Traces**: Traces with execution times over 5 seconds
- **Delayed Chain Traces**: Service chains with Service D consistently having high latency (3-4 seconds)

You can also manually trigger trace generation using the web UI. The application will continuously generate a mix of these trace types in the background at random intervals.

## Processing Pipeline

This example demonstrates a more complex trace processing pipeline with the following components:

1. **OTLP Receiver**: Receives traces from the application via gRPC or HTTP
2. **Batch Processor**: Groups spans for efficient processing
3. **Transform Processor**: Modifies trace data before storage (used to set the service name for raw traces)
4. **Tail Sampling Processor**: Applies sampling policies based on trace properties
5. **OTLP Exporter**: Sends sampled traces to Tempo

### Transform Processor

The transform processor modifies the service name attribute for raw traces to differentiate them from sampled traces:

```
otelcol.processor.transform "default" {
  error_mode = "ignore"

  trace_statements {
    context = "resource"
    statements = [
      `set(attributes["service.name"], "raw-traces")`,
    ]
  }

  output {
    traces  = [otelcol.exporter.otlp.tempo.input]
  }
}
```

This allows you to see both the original raw traces (with service.name="raw-traces") and the sampled traces (with service.name="trace-demo-tail-sampled") in Tempo.

## Tail Sampling Configuration

This example uses Alloy's `otelcol.processor.tail_sampling` processor, which makes sampling decisions based on the entire trace, not just individual spans. This allows for more intelligent sampling based on trace-wide properties.

The tail sampling configuration includes the following policies:

1. **Attribute-Based Sampling**: Samples traces with a specific attribute value
   ```
   policy {
     name = "test-attribute-policy"
     type = "string_attribute"
     
     string_attribute {
       key    = "test_attr_key_1"
       values = ["test_attr_val_1"]
     }
   }
   ```

2. **Error Sampling**: Always samples traces with ERROR status
   ```
   policy {
     name = "error-policy"
     type = "status_code"
     
     status_code {
       status_codes = ["ERROR"]
     }
   }
   ```

3. **Latency-Based Sampling**: Samples traces that exceed a latency threshold
   ```
   policy {
     name = "latency-policy"
     type = "latency"
     
     latency {
       threshold_ms = 5000  // 5 seconds
     }
   }
   ```

4. **Numerical Range Sampling**: Samples traces with a numeric attribute in a specific range
   ```
   policy {
     name = "numeric-policy"
     type = "numeric_attribute"
     
     numeric_attribute {
       key       = "key1"
       min_value = 70
       max_value = 100
     }
   }
   ```

5. **URL-Based Filtering**: Excludes health check and metrics endpoints
   ```
   policy {
     name = "url-filter-policy"
     type = "string_attribute"
     
     string_attribute {
       key             = "http.url"
       values          = ["/health", "/metrics"]
       invert_match    = true
     }
   }
   ```

6. **Probabilistic Sampling**: Samples a percentage of remaining traces
   ```
   policy {
     name = "probabilistic-policy"
     type = "probabilistic"
     
     probabilistic {
       sampling_percentage = 10
     }
   }
   ```

## Live Debugging

This example enables Alloy's live debugging feature, which provides real-time insights into the sampling process:

```
livedebugging {
  enabled = true
}
```

Access the live debugging interface at http://localhost:12345/debug/livedebugging to see:

- Current processing pipeline state
- Trace sampling decisions in real-time
- Policy hit counts and performance metrics
- Throughput statistics

## Sampling Implications

With tail sampling enabled in this example:

- All error traces are preserved for troubleshooting
- High latency traces (>5s) are kept for performance analysis
- Traces with specific attribute values used for monitoring are retained
- Health check and metrics endpoints are filtered out to reduce noise
- A small percentage of other traces are kept for baseline monitoring
- Traces not matching any criteria are dropped, reducing storage needs
- Raw traces are stored with a different service name for comparison

## Viewing Traces in Grafana

To view the sampled traces:

1. Open Grafana (http://localhost:3000)
2. Navigate to Explore
3. Select the Tempo data source
4. Use the Search tab to find traces based on various criteria
5. Try filtering by service name "trace-demo-tail-sampled" (sampled traces) vs "raw-traces" (all traces)

## Sample Queries

Try these queries in Grafana's Tempo Explorer:

- Find all traces for the sampled service:
  ```
  service.name="trace-demo-tail-sampled"
  ```

- Find all raw traces:
  ```
  service.name="raw-traces"
  ```

- Find error traces:
  ```
  status.code="error"
  ```

- Find high latency traces:
  ```
  duration > 5s
  ```

- Find traces with a specific attribute:
  ```
  test_attr_key_1="test_attr_val_1"
  ```
  
- Find traces with Service D bottleneck:
  ```
  service.latency="high" AND latency.category="bottleneck"
  ```

## Customizing

You can modify the `config.alloy` file to adjust the sampling policies:

- Change the decision wait time to balance memory usage vs. complete trace visibility
- Adjust the sampling thresholds to capture more or fewer traces
- Add additional sampling policies based on your specific needs
- Modify the existing policies to match your application's attributes
- Update the transform processor to add or modify different attributes

## Further Resources

- [Grafana Alloy Tail Sampling Documentation](https://grafana.com/docs/alloy/latest/reference/components/otelcol.processor.tail_sampling/)
- [Grafana Alloy Transform Processor Documentation](https://grafana.com/docs/alloy/latest/reference/components/otelcol.processor.transform/)
- [OpenTelemetry Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor)
- [Live Debugging in Grafana Alloy](https://grafana.com/docs/alloy/latest/debug-alloy-flow/) 