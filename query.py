import asyncio
import asyncpg
import json

async def main():
    conn = await asyncpg.connect(user="otimiz_admin", password="otimiz_password", database="otimiz_db", host="localhost", port=5444)
    for id_ in [420, 421]:
        val = await conn.fetchval(f"SELECT metadata FROM schedules WHERE id = {id_}")
        if val:
            meta = json.loads(val)
            print(f"--- ID {id_} ---")
            print("chosen_scenario:", meta.get("chosen_scenario"))
            if "operational_quality_decision" in meta:
                print("operational_quality_decision keys:", meta["operational_quality_decision"].keys())
                print("improvements:", meta["operational_quality_decision"].get("chosen_scenario"))
                with open(f"/tmp/db_meta_{id_}.json", "w") as f:
                    json.dump(meta, f, indent=2)

asyncio.run(main())
