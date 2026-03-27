# Use Node LTS
FROM node:20

# Create app directory
WORKDIR /app

# Copy package files first (for caching)
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the app
COPY . .

# Expose dev server port
EXPOSE 3000

# Start the app
CMD ["npm", "run", "dev"]
