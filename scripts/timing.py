import time

from step2_llm import graph

for level_ticket in ["Is my room at the Skylight confirmed? Ref ET-5520",
                     "The shuttle never came and I waited two hours!"]:
    start = time.perf_counter()
    out = graph.invoke({"ticket": level_ticket})
    print(f"{time.perf_counter() - start:5.1f}s  {out['category']}")