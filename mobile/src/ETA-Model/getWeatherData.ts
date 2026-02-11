import { fetchWeatherApi } from "openmeteo";
import * as fs from "fs";
import * as path from "path";

const params = {
	latitude: 32.61,
	longitude: -85.48,
	hourly: ["precipitation", "precipitation_probability", "temperature_2m"],
	timezone: "America/Chicago",
	start_date: "2025-11-06",
	end_date: "2026-01-14",
};
const url = "https://api.open-meteo.com/v1/forecast";
const responses = await fetchWeatherApi(url, params);

// Process first location. Add a for-loop for multiple locations or weather models
const response = responses[0];

// Attributes for timezone and location
const latitude = response.latitude();
const longitude = response.longitude();
const elevation = response.elevation();
const timezone = response.timezone();
const timezoneAbbreviation = response.timezoneAbbreviation();
const utcOffsetSeconds = response.utcOffsetSeconds();

console.log(
	`\nCoordinates: ${latitude}°N ${longitude}°E`,
	`\nElevation: ${elevation}m asl`,
	`\nTimezone: ${timezone} ${timezoneAbbreviation}`,
	`\nTimezone difference to GMT+0: ${utcOffsetSeconds}s`,
);

const hourly = response.hourly()!;

// Note: The order of weather variables in the URL query and the indices below need to match!
const weatherData = {
	hourly: {
		time: Array.from(
			{ length: (Number(hourly.timeEnd()) - Number(hourly.time())) / hourly.interval() }, 
			(_, i) => new Date((Number(hourly.time()) + i * hourly.interval() + utcOffsetSeconds) * 1000)
		),
		precipitation: hourly.variables(0)!.valuesArray(),
		precipitation_probability: hourly.variables(1)!.valuesArray(),
		temperature_2m: hourly.variables(2)!.valuesArray(),
	},
};

// The 'weatherData' object now contains a simple structure, with arrays of datetimes and weather information
console.log("\nHourly data:\n", weatherData.hourly);

// Create raw_data directory if it doesn't exist
const rawDataDir = path.join(import.meta.dirname, "raw_data");
if (!fs.existsSync(rawDataDir)) {
	fs.mkdirSync(rawDataDir, { recursive: true });
}

// Convert to CSV format
const csvHeader = "time,precipitation,precipitation_probability,temperature_2m";
const csvRows = weatherData.hourly.time.map((time, i) => {
	return [
		time.toISOString(),
		weatherData.hourly.precipitation![i],
		weatherData.hourly.precipitation_probability![i],
		weatherData.hourly.temperature_2m![i],
	].join(",");
});

const csvContent = [csvHeader, ...csvRows].join("\n");
const csvPath = path.join(rawDataDir, "weather_data.csv");
fs.writeFileSync(csvPath, csvContent);
console.log(`\nSaved weather data to ${csvPath}`);