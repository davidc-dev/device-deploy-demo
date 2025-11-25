{{/*
Expand the name of the chart.
*/}}
{{- define "device-workflow.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "device-workflow.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Backend/Frontend specific names
*/}}
{{- define "device-workflow.backendName" -}}
{{- printf "%s-backend" (include "device-workflow.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "device-workflow.frontendName" -}}
{{- printf "%s-frontend" (include "device-workflow.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
