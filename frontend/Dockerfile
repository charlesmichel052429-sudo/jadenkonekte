# Front web statique servi par nginx, qui relaie /api vers le service api (même origine : pas de CORS)
FROM nginx:1.27-alpine
# Chart.js embarqué dans l'image (version figée) : pas de dépendance à un CDN au chargement de la page
ADD https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js /usr/share/nginx/html/vendor/chart.umd.min.js
RUN chmod 644 /usr/share/nginx/html/vendor/chart.umd.min.js
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/public/ /usr/share/nginx/html/
