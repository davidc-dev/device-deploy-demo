FROM registry.redhat.io/ubi8/nodejs-20 AS build

WORKDIR /opt/app-root/src

ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY frontend-workflow-app/package*.json ./
RUN npm ci

COPY frontend-workflow-app/ .
RUN npm run build

FROM registry.redhat.io/ubi9/nginx-120

COPY --from=build /opt/app-root/src/dist /opt/app-root/src

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
