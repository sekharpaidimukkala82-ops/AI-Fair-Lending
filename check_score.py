import sys, os
sys.path.insert(0, '.')
os.environ['DISABLE_FASTEMBED'] = 'true'
import pandas as pd
from backend.core.fairness_engine import FairnessEngine

engine = FairnessEngine()
df = pd.read_csv('sample_data/moderate_bias_demo.csv')
report = engine.generate_audit(df)
print(f'Score: {report.score}')
print(f'DI ratios: {report.disparate_impact_ratios}')
print(f'Bias indicators: {len(report.bias_indicators)}')
for f in report.findings:
    print(f'  {f}')
