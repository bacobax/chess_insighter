import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("login", "routes/login.tsx"),
  route("signup", "routes/signup.tsx"),
  route("verify-email", "routes/verify-email.tsx"),
  route("dashboard", "routes/dashboard.tsx"),
  route("games/:username", "routes/games.$username.tsx"),
  route("report/:username/reports/new", "routes/report.$username.reports.new.tsx"),
  route("report/:username/reports/:reportId/mistake/:mistakeId", "routes/report.$username.mistake.$mistakeId.tsx"),
  route("report/:username/reports/:reportId", "routes/report.$username.reports.$reportId.tsx"),
  route("report/:username", "routes/player-dossier.tsx"),
  route("opening-study", "routes/opening-study.tsx"),
] satisfies RouteConfig;
