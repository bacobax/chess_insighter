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

export type OpeningReportGroup = {
  opening_characteristics: MetricPoint[];
};

export type ReportCharts = {
  skill_profile: MetricPoint[];
  favourite_openings: OpeningCount[];
  opening_characteristics: MetricPoint[];
  opening_report_groups: Record<"white" | "black" | "both", OpeningReportGroup>;
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
  analysis_context: ReportAnalysisContext | null;
};

export type ReportBuildRequest = {
  username: string;
  hparams: Hparams;
  max_games: number;
  engine_depth: number;
  use_engine: boolean;
  refresh_cache: boolean;
  target_color?: "white" | "black" | "both";
  time_classes?: string[] | null;
  rated_filter?: boolean | null;
  since_year?: number | null;
  since_month?: number | null;
  until_year?: number | null;
  until_month?: number | null;
};

export type ReportAnalysisContext = {
  games: GameSummary[];
  default_game_ids: string[];
  engine_depth: number;
  engine_enriched: boolean;
  sidecar_id?: string | null;
};

export type ReportMistakesSelectionRequest = {
  selected_game_ids: string[];
  engine_depth: number;
  max_punishment_plies: number;
  picker_filters?: Record<string, JsonValue> | null;
};

export type ReportGamesCatalogRequest = {
  page: number;
  page_size: number;
  time_classes?: string[] | null;
  rated_filter?: boolean | null;
  since_year?: number | null;
  since_month?: number | null;
  until_year?: number | null;
  until_month?: number | null;
  result_filter?: ("win" | "loss" | "draw" | "unknown")[] | null;
};

export type TacticTag = {
  theme: string;
  move_uci: string;
  ply_offset: number;
  confidence: number;
  evidence: Record<string, JsonValue>;
};

export type PunishmentLineMove = {
  ply_offset: number;
  side_to_move: "white" | "black";
  move_uci: string;
  san: string;
  fen_before: string;
  fen_after: string;
  eval_cp: number | null;
  user_eval_cp: number | null;
  user_win_prob: number | null;
  top_move_gap_cp: number | null;
  eval_volatility_cp: number | null;
  retained_wp_loss: number | null;
  stable_after_move: boolean;
  tactics: TacticTag[];
  mate_in?: number | null;
};

export type MistakeAnalysisItem = {
  mistake_id: string;
  game_uuid: string | null;
  game_url: string | null;
  ply: number;
  move_number: number;
  player_color: "white" | "black";
  san: string;
  uci: string;
  fen_before: string;
  fen_after: string;
  severity: "none" | "inaccuracy" | "mistake" | "blunder" | string;
  cp_loss: number | null;
  wp_loss: number | null;
  user_eval_before_cp: number | null;
  user_eval_after_cp: number | null;
  win_prob_before: number | null;
  win_prob_after: number | null;
  best_line: string[];
  best_line_moves: PunishmentLineMove[];
  theoretical_punishment_depth: number;
  theoretical_punishment_plies: number;
  punishment_difficulty: number;
  stability_reached: boolean;
  actual_punished: boolean;
  actual_punishing_moves_played: number;
  missed_at_ply: number | null;
  missed_best_move_uci: string | null;
  missed_actual_move_uci: string | null;
  actual_line_moves: PunishmentLineMove[];
  tactics: TacticTag[];
  actual_tactics: TacticTag[];
  user_rating?: number;
  mate_before?: number | null;
  mate_after?: number | null;
};

export type MistakesAnalysisSummary = {
  games_analyzed: number;
  target_moves_analyzed: number;
  mistake_count: number;
  severity_counts: Record<string, number>;
  theme_counts: Record<string, number>;
  average_theoretical_punishment_depth: number | null;
  actual_punished_count: number;
};

export type ReportMistakesResponse = {
  analysis_hash: string;
  cache_hit: boolean;
  selected_games: GameSummary[];
  metadata: Record<string, JsonValue>;
  summary: MistakesAnalysisSummary;
  mistakes: MistakeAnalysisItem[];
};

export type ReportGamesCatalogResponse = GamesQueryResponse & {
  cache_hit: boolean;
};

export type ReportMistakeDetailResponse = {
  analysis_hash: string;
  mistake: MistakeAnalysisItem;
  selected_games: GameSummary[];
  metadata: Record<string, JsonValue>;
};

export type ReportBuildResponse = {
  cache_hash: string;
  cache_hit: boolean;
  normalized_hparams: Hparams;
  report: ReportPayload;
  report_id: string | null;
  saved: boolean;
  title: string | null;
  request_params: ReportBuildRequest | null;
};

export type ReportBuildJobAccepted = {
  build_id: string;
  socket_token: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
};

export type ReportBuildJobStatus = {
  build_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  stage: string;
  progress: number;
  message: string;
  revision: number;
  processed: number | null;
  total: number | null;
  report_id: string | null;
  error: string | null;
};

export type AuthUser = {
  id: string;
  email: string;
  created_at: string;
  verified_at: string;
};

export type RegisterResponse = {
  registration_id: string;
  socket_token: string;
  expires_at: string;
};

export type ReportSummary = {
  id: string;
  username: string;
  generated_label: string;
  title: string | null;
  cache_hash: string;
  games_analyzed: number;
  request_params: ReportBuildRequest & Record<string, JsonValue>;
  created_at: string;
  updated_at: string;
  saved_at: string;
};

export type DashboardPlayer = {
  username: string;
  report_count: number;
  latest_report_at: string;
  reports: ReportSummary[];
};

export type DashboardResponse = {
  user: AuthUser;
  report_count: number;
  player_count: number;
  latest_activity_at: string | null;
  players: DashboardPlayer[];
};

export type PlayerReportsResponse = {
  username: string;
  reports: ReportSummary[];
};

export type SavedReportEntry = {
  cache_hash: string;
  username: string;
  created_at: string;
  last_refreshed_at: string;
  games_analyzed: number;
  request_params: ReportBuildRequest & Record<string, JsonValue>;
};

export type SavedReportsList = {
  entries: SavedReportEntry[];
};

export type SaveReportRequest = {
  cache_hash: string;
  username: string;
  games_analyzed: number;
  request_params: ReportBuildRequest;
};

// ---------------------------------------------------------------------------
// Mistakes Analyzer — Position Analysis
// ---------------------------------------------------------------------------

export type EngineLinePreview = {
  rank: number;
  first_uci: string;
  first_san: string;
  line_san: string[];
  line_uci: string[];
  eval_cp: number | null;
  mate_in: number | null;
  user_win_prob: number | null;
  user_eval_cp: number | null;
};

export type PositionAnalysis = {
  top_lines: EngineLinePreview[];
  optimal_line: PunishmentLineMove[];
};

export type MistakePositionRequest = {
  fen: string;
  player_color: "white" | "black";
  rating?: number;
  engine_depth?: number;
  max_plies?: number;
};

// ---------------------------------------------------------------------------
// Opening Study Suggestion Tree
// ---------------------------------------------------------------------------

export type TargetColor = "white" | "black";
export type StudySimilarityType = "cosine" | "dot_product";
export type MatchMode = "style" | "custom";
export type EvaluationMetric = "engine" | "practical";
export type OpponentMoveOrdering = "engine" | "popularity";

export type MatcherFeatureKey =
  | "tactical_density"
  | "quiet_position_density"
  | "king_safety_risk"
  | "early_castling_tendency"
  | "opposite_side_castling_tendency"
  | "middlegame_complexity"
  | "pawn_structure_sharpness"
  | "material_imbalance"
  | "endgame_likelihood_proxy";

export type OpeningStudyWeights = {
  playerStyleMatch?: number;
  engineSoundness?: number;
  aggressiveness?: number;
  practicalGamble?: number;
  systemness?: number;
  memorySimplicity?: number;
};

export type OpeningStudyTreeChildrenRequest = {
  /** Preferred source: hash from a /api/report/build response. Uses the
   *  player vector computed from the exact games+filters of that report. */
  cacheHash?: string;
  reportId?: string;
  /** Fallback: username lookup in the flat player_vectors.json cache.
   *  Ignores game filters; uses whichever vector was cached most recently. */
  username?: string;
  playerVectorCachePath?: string;
  openingVectorsPath?: string;
  targetColor: TargetColor;
  prefixUci: string[];
  topK: number;
  opponentTopK: number;
  opponentMoveOrdering?: OpponentMoveOrdering;
  weights?: OpeningStudyWeights;
  similarityType?: StudySimilarityType;
  weightedMatching?: boolean;
  matcherWeights?: Partial<Record<MatcherFeatureKey, number>>;
  matchMode?: MatchMode;
  evaluationMetric?: EvaluationMetric;
  evaluationThreshold?: number;
};

export type MetricComponent = {
  key: string;
  label: string;
  value: number;
  weight: number;
  rawValue?: number | null;
  rawUnit?: string | null;
};

export type StyleMatchComponent = {
  key: string;
  label: string;
  playerValue: number;
  openingValue: number;
  weight: number;
};

export type NodeBreakdown = {
  aggressiveness?: MetricComponent[];
  memoryComplexity?: MetricComponent[];
  systemness?: MetricComponent[];
  engineSoundness?: MetricComponent[];
  playerStyleMatch?: StyleMatchComponent[];
  openingFeatures?: Record<string, number>;
};

export type OpeningStudyTreeNode = {
  id: string;
  moveUci: string;
  moveSan: string;
  fen: string;
  prefixUci: string[];
  compatibleLineCount: number;
  openingNames: string[];
  representativeUci?: string | null;
  representativePgn?: string | null;
  playerStyleMatch: number;
  engineSoundness: number;
  popularityScore: number;
  popularityGames: number;
  aggressiveness: number;
  practicalGamble: number | null;
  practicalGambleRaw: number | null;
  practicalGambleSampleSize: number;
  practicalGambleCoverage: number;
  memoryComplexity: number;
  systemness: number;
  studyScore: number;
  sideToMove: "white" | "black";
  targetColor: TargetColor;
  isTargetMove: boolean;
  boardPreviewFen: string;
  stats: {
    playerStyleMatch: number;
    engineSoundness: number;
    aggressiveness: number;
    practicalGamble: number | null;
    memoryComplexity: number;
    systemness: number;
  };
  breakdown?: NodeBreakdown;
  explanation?: NodeExplanation;
};

export type NodeExplanationFactor = {
  key: "playerStyleMatch" | "aggressiveness" | "systemness" | "memorySimplicity" | string;
  label: string;
  /** Criterion value (0-100), oriented so higher raises the score. */
  value: number;
  referenceValue: number;
  /** Share of the score gap to `comparedTo`, in score points. */
  contribution: number;
};

/** Plain-language "why this score / why this order" relative to the siblings. */
export type NodeExplanation = {
  summary: string;
  comparedTo: string | null;
  scoreGap: number | null;
  factors: NodeExplanationFactor[];
  highlights: string[];
  feasibility: string | null;
};

export type OpeningStudyTreeChildrenResponse = {
  targetColor: TargetColor;
  prefixUci: string[];
  children: OpeningStudyTreeNode[];
  vectorSource?: string | null;
  playerVector?: Record<string, number> | null;
};

export type TrainingTimeClass = "bullet" | "blitz" | "rapid" | "daily";

export type TrainingPlanBuildRequest = {
  username: string;
  max_games: number;
  time_classes: TrainingTimeClass[] | null;
  engine_depth: number;
};

export type TrainingProcessTag = {
  tag: string;
  title: string;
  count: number;
  rate_per_100: number;
  share: number;
  avg_wp_loss: number | null;
};

export type TrainingWeakness = TrainingProcessTag & {
  definition: string;
  training: string;
  secondary: string;
};

export type TrainingContextRow = { bucket: string; moves: number; errors: number; rate_per_100: number };

export type TrainingDiagnosis = {
  moves_analyzed: number;
  error_count: number;
  blunder_count: number;
  rate_per_100: number;
  process_tags: TrainingProcessTag[];
  top_weaknesses: TrainingWeakness[];
  domains: { domain: "opening" | "middlegame_tactics" | "middlegame_positional" | "endgame"; count: number; share: number }[];
  motifs: { motif: string; count: number; games: number; own_block: boolean }[];
  context: Record<string, TrainingContextRow[]>;
  insights: { headline: string; detail: string }[];
};

export type TrainingOpeningPlayed = {
  slot: string;
  slot_label: string;
  choice: string;
  name: string;
  eco: string | null;
  moves: string;
  games: number;
  score: number;
  avg_eval_at_15: number | null;
  first_error_move: number | null;
  verdict: "fix_first" | "middlegame" | "keep" | "consolidate" | "ignore";
};

export type TrainingOpeningRecommendation = {
  slot: string;
  slot_label: string;
  name: string;
  line: string;
  learn_depth: string;
  why: string;
  plans: string | null;
  trap: string | null;
  your_games: number;
  your_score: number | null;
  replaces: string[];
};

export type TrainingBlock = { kind: string; label: string; minutes: number; text: string };

export type TrainingDay = {
  day: string;
  focus: string;
  session: string;
  weakness: string | null;
  blocks: TrainingBlock[];
  minutes: number;
};

export type TrainingCard = {
  card_id: string;
  game_url: string | null;
  game_end_time: number | null;
  opponent: string | null;
  player_color: "white" | "black";
  move_number: number;
  ply: number;
  fen_before: string;
  played_san: string;
  played_uci: string;
  best_san: string | null;
  best_uci: string | null;
  refutation_san: string[];
  wp_loss: number | null;
  severity: string;
  process: string;
  domain: string;
  motifs: string[];
  clock_fraction: number | null;
  eval_before_cp: number | null;
  due_on: string;
  interval_days: number;
  streak: number;
  reviews: number;
  retired: boolean;
  label: string | null;
  note: string | null;
};

export type TrainingPlan = {
  id: string;
  username: string;
  request_params: TrainingPlanBuildRequest;
  created_at: string;
  updated_at: string;
  metadata: {
    username: string;
    games_analyzed: number;
    moves_analyzed: number;
    rating: number | null;
    time_classes: Record<string, number>;
    score: number;
    created_on: string;
    reevaluate_on: string;
    games_removed: number;
    engine_depth: number | null;
    requested_games: number | null;
    requested_time_classes: string[] | null;
  };
  diagnosis: TrainingDiagnosis;
  repertoire: {
    mode: "simple" | "theory";
    reasons: string[];
    played: TrainingOpeningPlayed[];
    recommended: TrainingOpeningRecommendation[];
  };
  routine: {
    base_minutes: number;
    days: TrainingDay[];
    puzzle_split: { mixed: number; themed: number; themed_motifs: string[] };
    rules: string[];
  };
  cards: TrainingCard[];
};

export type TrainingCardReviewRequest = {
  grade: "again" | "hard" | "good";
  label?: string | null;
  note?: string | null;
};

export type OpeningDrillLine = {
  id: string;
  probability: number;
  main_line: boolean;
  moves: string[];
  user_color: "white" | "black";
  eco: string | null;
  variation: string | null;
  deviates_at: number | null;
  opponent_choices: { ply: number; san: string; share: number | null; main_line: boolean; alternatives: { san: string; share: number }[] }[];
};

export type OpeningDrillCatalog = { lines: OpeningDrillLine[] };

// --- Repertoire (saved moves by position, lines, drill) -------------------------------

export type RepertoireColor = "white" | "black";

export type RepertoireMove = {
  uci: string;
  san: string;
  games: number;
  share: number;
  /** Engine eval after the move, from your side (centipawns). */
  cp: number | null;
  mate: number | null;
  /** How far behind the engine's best move. */
  cpLoss: number | null;
  engineRank: number | null;
  /** Within your tolerance and eval floor; null when the engine has not checked it. */
  playable: boolean | null;
  openingEco: string | null;
  openingName: string | null;
  inCatalog: boolean;
};

export type RepertoirePosition = {
  status: "ready" | "pending";
  retryAfter: number | null;
  messages: string[];
  color: RepertoireColor;
  prefixUci: string[];
  fen: string;
  epd: string;
  ply: number;
  sideToMove: RepertoireColor;
  ownTurn: boolean;
  opening: { eco: string | null; name: string; ply: number; exact: boolean } | null;
  inCatalog: boolean;
  /** Catalogued move order reaching this position, for Opening Lab scores. */
  labPrefixUci: string[] | null;
  popularity: { source: "snapshot" | "live" | "none"; status: "ready" | "pending" | "unavailable"; totalGames: number; fetchedAt: string | null; outOfBook: boolean };
  engine: { status: "ready" | "pending" | "unavailable" | "skipped"; depth: number; bestMove: string | null; evalCp: number | null };
  moves: RepertoireMove[];
  settings: { cpTolerance: number; minEvalCp: number };
};

export type RepertoireChoice = {
  uci: string;
  san: string;
  prefixUci: string[];
  cp: number | null;
  cpLoss: number | null;
  depth: number | null;
  source: "user" | "seed";
  chosenAt: string;
};

export type RepertoireSettings = {
  cpTolerance: number;
  minEvalCp: number;
  minReach: number;
  maxOwnMoves: number;
};

export type Repertoire = {
  color: RepertoireColor;
  /** Keyed by position (EPD). */
  choices: Record<string, RepertoireChoice>;
  settings: RepertoireSettings;
  updatedAt: string | null;
};

export type RepertoireLineStatus = "complete" | "out_of_book" | "needs_choice" | "pending" | "no_data";

export type RepertoireLine = {
  id: string;
  prefixUci: string[];
  san: string[];
  /** Share of your games in which you meet this line. */
  reach: number;
  status: RepertoireLineStatus;
  endReason: "move_cap" | "no_common_reply" | "game_over" | "depth_limit" | null;
  ownMoves: number;
  epd: string;
  openingEco: string | null;
  openingName: string | null;
};

export type RepertoireLines = {
  color: RepertoireColor;
  startPrefixUci: string[];
  lines: RepertoireLine[];
  coverage: { complete: number; outOfBook: number; needsChoice: number; pending: number; noData: number; pruned: number };
  status: "ready" | "pending";
  retryAfter: number | null;
  choicesUsed: number;
  truncated: boolean;
  settings: { minReach: number; maxOwnMoves: number };
};
