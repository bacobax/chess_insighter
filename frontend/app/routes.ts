import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("games/:username", "routes/games.$username.tsx"),
  route("report/:username", "routes/report.$username.tsx"),
  route("opening-study", "routes/opening-study.tsx"),
] satisfies RouteConfig;
