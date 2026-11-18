# syntax=docker/dockerfile:1

# ---- build stage ----
FROM node:20-alpine AS build

WORKDIR /app

# Vite inlines this at build time, so it must be the URL the BROWSER uses to reach the backend, not a container name.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# package*.json matches package-lock.json when it exists; without a lockfile, fall back to a normal install.
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

# `npm run build` runs `tsc --noEmit` followed by `vite build`, so a type error fails the image build.
RUN npm run build


# ---- runtime stage ----
FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["wget", "-q", "--spider", "http://127.0.0.1/healthz"]
