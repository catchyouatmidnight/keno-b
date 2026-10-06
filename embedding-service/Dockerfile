FROM node:22-bookworm-slim
WORKDIR /app
COPY package.json ./
RUN ONNXRUNTIME_NODE_INSTALL_CUDA=skip npm install --omit=dev
COPY server.mjs ./
USER node
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD node -e "fetch('http://127.0.0.1:8080/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node","server.mjs"]
