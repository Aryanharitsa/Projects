from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/graph")
def graph():
    # dummy nodes & edges
    data = {
        "nodes": [{"id": "A"}, {"id": "B"}],
        "edges": [{"source": "A", "target": "B"}]
    }
    return jsonify(data)

if __name__ == "__main__":
    app.run(port=5000, debug=True)