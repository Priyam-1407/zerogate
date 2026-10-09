from fastapi import FastAPI

app = FastAPI()

@app.get("/salaries")
def salaries():
    return {"data": [{"name": "Priyam", "salary": 50000}, {"name": "Rahul", "salary": 60000}]}