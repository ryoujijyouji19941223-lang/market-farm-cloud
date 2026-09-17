import pandas as pd
from market_farm.sensors import price_sensor, probability

def test_uptrend():
    df=pd.DataFrame({"Close":[100+i for i in range(30)]})
    s=price_sensor(df)
    assert s["price_score"]>0
    assert probability(s["price_score"])>.5
