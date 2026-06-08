export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type Hparams = Record<string, JsonValue>;

export type GameSummary = {
  id: string | null;
  url: string | null;
  result: "win" | "loss" | "draw" | "unknown";
  player_username: string;
  player_color: "white" | "black";
  player_elo_before: number | null;
  player_elo_after: number | null;
  opponent_username: string | null;
  opponent_elo_before: number | null;
  opponent_elo_after: number | null;
  opponent_result: string | null;
  end_time: number | null;
  end_time_iso: string | null;
  time_class: string | null;
  time_control: string | null;
  rated: boolean | null;
  opening_eco: string | null;
  opening_name: string | null;
};

export type GamesQueryRequest = {
  username: string;
  page: number;
  page_size: number;
  time_classes?: string[] | null;
  rated_filter?: boolean | null;
  since_year?: number | null;
  since_month?: number | null;
  until_year?: number | null;
  until_month?: number | null;
};

export type GamesQueryResponse = {
  items: GameSummary[];
  page: number;
  page_size: number;
  has_more: boolean;
  total_loaded: number;
};

export type MetricPoint = {
  key: string;
  label: string;
  value: number | null;
  direction: "higher" | "lower";
};

export type OpeningCount = {
  name: string;
  count: number;
  color: "white" | "black";
};

export type OpeningFeatureSet = {
  opening_name: string;
  color: "white" | "black";
  count: number;
  family_name: string | null;
  features: MetricPoint[];
};

export type OpeningMatch = {
  opening_name: string;
  similarity_score: number | null;
  eco_values: string | null;
  line_count: number | null;
  representative_pgn: string | null;
  representative_uci: string | null;
  fen: string | null;
  used_features: string[];
};

export type ReportCharts = {
  skill_profile: MetricPoint[];
  favourite_openings: OpeningCount[];
  top_opening_features: OpeningFeatureSet[];
  opening_characteristics: MetricPoint[];
  top_opening_matches: OpeningMatch[];
  opening_components: MetricPoint[];
  time_management_indicators: MetricPoint[];
  advantage_capitalization_components: MetricPoint[];
  resourcefulness_components: MetricPoint[];
  game_analysis_components: MetricPoint[];
  average_time_by_complexity: MetricPoint[];
};

export type ReportPayload = {
  metadata: Record<string, JsonValue>;
  statistics_bundle: Record<string, JsonValue>;
  charts: ReportCharts;
};

export type ReportBuildRequest = {
  username: string;
  hparams: Hparams;
  max_games: number;
  engine_depth: number;
  use_engine: boolean;
  refresh_cache: boolean;
  time_classes?: string[] | null;
  rated_filter?: boolean | null;
  since_year?: number | null;
  since_month?: number | null;
  until_year?: number | null;
  until_month?: number | null;
};

export type ReportBuildResponse = {
  cache_hash: string;
  cache_hit: boolean;
  normalized_hparams: Hparams;
  report: ReportPayload;
};
