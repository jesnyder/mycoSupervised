// Weather data for mycoSupervised study periods
// Source: Open-Meteo Historical Weather API (https://open-meteo.com/)
// ERA5 reanalysis data, hourly.
//
// Stale entries for the prior astroPharmReactor E. coli studies (study001_ecoli,
// study002_ecoli) have been removed. Populate window.WEATHER_DATA["study001_pilot"]
// with { time, temperature_2m, surface_pressure } arrays for the study location
// to enable the weather-overlay chart on the dashboard.

window.WEATHER_DATA = window.WEATHER_DATA || {};
