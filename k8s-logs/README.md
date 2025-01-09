
# Monitor Kubernetes Logs with Grafana Alloy and Loki

This scenario demonstrates how to monitor Kubernetes logs using Grafana Alloy and Loki. This scenario will install three Helm charts: Loki, Grafana, and Alloy. Loki will be used to store the logs, Grafana will be used to visualize the logs, and Alloy will be used to collect three different log sources:
* Pod Logs
* Kubernetes Events
* System / Node Logs

## Prerequisites

Clone the repository:

```bash
git clone https://github.com/grafana/alloy-scenarios.git
```

Change to the directory:

```bash
cd alloy-scenarios/k8s-logs
```

Next you will need a Kubernetes cluster (In this example, we will configure a local Kubernetes cluster using [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/))

An example kind cluster configuration is provided in the `kind.yml` file. To create a kind cluster using this configuration, run the following command:

```bash
kind create cluster --config kind.yml
```

Lastly you will need to make sure you install Helm on your local machine. You can install Helm by following the instructions [here](https://helm.sh/docs/intro/install/). You will also need to install the Grafana Helm repository:

```bash
helm repo add grafana https://grafana.github.io/helm-charts
```

## Install the Loki Helm Chart

The first step is to install the Loki Helm chart. This will install Loki in the `meta` namespace. The `loki-values.yml` file contains the configuration for the Loki Helm chart. To install Loki, run the following command:

```bash
helm install --values loki-values.yml loki grafana/loki -n meta --create-namespace
```

This installs Loki in monolithic mode. For more information on Loki modes, see the [Loki documentation](https://grafana.com/docs/loki/latest/get-started/deployment-modes/).

## Install the Grafana Helm Chart

The next step is to install the Grafana Helm chart. This will install Grafana in the `meta` namespace. The `grafana-values.yml` file contains the configuration for the Grafana Helm chart. To install Grafana, run the following command:

```bash
helm install --values grafana-values.yml grafana grafana/grafana --namespace meta
```
Note that within the `grafana-values.yml` file, the `grafana.ini` configuration is set to use the Loki datasource. This is done by setting the `datasources.datasources.yaml` field to the Loki datasource configuration.

## Install the Alloy Helm Chart

The final step is to install the Alloy Helm chart. This will install Alloy in the `meta` namespace. The `alloy-values.yml` file contains the configuration for the Alloy Helm chart. To install Alloy, run the following command:

```bash
helm install --values alloy-values.yml alloy grafana/alloy --namespace meta
```
Within the `alloy-values.yml` file we declare the Alloy configuration. This configuration specifies the log sources that Alloy will collect logs from. In this scenario, we are collecting logs from three different sources: Pod Logs, Kubernetes Events, and System / Node Logs.

## Accessing the Grafana UI

To access the Grafana UI, you will need to port-forward the Grafana pod to your local machine. First, get the name of the Grafana pod:

```bash
export POD_NAME=$(kubectl get pods --namespace meta -l "app.kubernetes.io/name=grafana,app.kubernetes.io/instance=grafana" -o jsonpath="{.items[0].metadata.name}")
```

Next, port-forward the Grafana pod to your local machine:

```bash
kubectl --namespace meta port-forward $POD_NAME 3000
```

Open your browser and go to [http://localhost:3000](http://localhost:3000). You can log in with the default username `admin` and password `adminadminadmin`.

## Accessing the Alloy UI

To access the Alloy UI, you will need to port-forward the Alloy pod to your local machine. First, get the name of the Alloy pod:

```bash
export POD_NAME=$(kubectl get pods --namespace meta -l "app.kubernetes.io/name=alloy,app.kubernetes.io/instance=alloy" -o jsonpath="{.items[0].metadata.name}")
```

Next, port-forward the Alloy pod to your local machine:

```bash
kubectl --namespace meta port-forward $POD_NAME 12345
```

## View the logs using Explore Logs in Grafana

Explore Logs is a new feature in Grafana which provides a queryless way to explore logs. To access Explore Logs. To access Explore logs open a browser and go to [http://localhost:3000/a/grafana-lokiexplore-app](http://localhost:3000/a/grafana-lokiexplore-app).