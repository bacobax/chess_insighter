import chess
import chess.engine

board = chess.Board()

engine = chess.engine.SimpleEngine.popen_uci("/opt/homebrew/bin/stockfish")  # Apple Silicon
# engine = chess.engine.SimpleEngine.popen_uci("/usr/local/bin/stockfish")   # Intel Mac

result = engine.analyse(
    board,
    chess.engine.Limit(time=0.1)  # low CPU cost
)

print(result["score"])
print(result.get("pv"))

engine.quit()