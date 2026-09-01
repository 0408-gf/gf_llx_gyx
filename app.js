const defaults = { homeName: '曼彻斯特蓝', awayName: '伦敦红', homeAttack: 82, homeDefense: 76, homeForm: 88, awayAttack: 79, awayDefense: 72, awayForm: 68 };
const metricIds = ['homeAttack', 'homeDefense', 'homeForm', 'awayAttack', 'awayDefense', 'awayForm'];

function syncRange(range) {
  const percentage = ((range.value - range.min) / (range.max - range.min)) * 100;
  range.style.background = `linear-gradient(90deg, var(--ink) ${percentage}%, #e4e7e1 ${percentage}%)`;
  document.getElementById(`${range.id}Output`).value = range.value;
}

metricIds.forEach((id) => {
  const range = document.getElementById(id);
  range.addEventListener('input', () => syncRange(range));
  syncRange(range);
});

function poisson(goals, expected) {
  let factorial = 1;
  for (let i = 2; i <= goals; i += 1) factorial *= i;
  return (Math.exp(-expected) * expected ** goals) / factorial;
}

function calculatePrediction() {
  const value = (id) => Number(document.getElementById(id).value);
  const homeBoost = document.getElementById('homeAdvantage').checked ? 1.12 : 1;
  const homeXg = Math.max(0.2, Math.min(4.5, 1.35 * (value('homeAttack') / value('awayDefense')) * (value('homeForm') / 70) * homeBoost));
  const awayXg = Math.max(0.2, Math.min(4.5, 1.2 * (value('awayAttack') / value('homeDefense')) * (value('awayForm') / 70)));
  let homeWin = 0; let draw = 0; let awayWin = 0; let best = { probability: 0, home: 0, away: 0 };

  for (let home = 0; home <= 10; home += 1) {
    for (let away = 0; away <= 10; away += 1) {
      const probability = poisson(home, homeXg) * poisson(away, awayXg);
      if (home > away) homeWin += probability;
      else if (home === away) draw += probability;
      else awayWin += probability;
      if (probability > best.probability) best = { probability, home, away };
    }
  }

  const total = homeWin + draw + awayWin;
  const probabilities = [homeWin / total, draw / total, awayWin / total];
  const percentages = probabilities.map((item) => Math.round(item * 100));
  percentages[0] += 100 - percentages.reduce((sum, item) => sum + item, 0);
  const labels = ['主队获胜', '双方战平', '客队获胜'];
  const winnerIndex = probabilities.indexOf(Math.max(...probabilities));
  const homeName = document.getElementById('homeName').value.trim();
  const awayName = document.getElementById('awayName').value.trim();

  document.getElementById('resultHomeName').textContent = homeName;
  document.getElementById('resultAwayName').textContent = awayName;
  document.getElementById('homeScore').textContent = best.home;
  document.getElementById('awayScore').textContent = best.away;
  document.getElementById('verdictText').textContent = labels[winnerIndex];
  document.getElementById('confidenceText').textContent = `置信度 ${percentages[winnerIndex]}%`;
  document.getElementById('xgText').textContent = `${homeXg.toFixed(2)} — ${awayXg.toFixed(2)}`;
  ['home', 'draw', 'away'].forEach((name, index) => {
    document.getElementById(`${name}Prob`).textContent = `${percentages[index]}%`;
    document.getElementById(`${name}Bar`).style.width = `${percentages[index]}%`;
  });
  const formGap = value('homeForm') - value('awayForm');
  document.getElementById('insightText').textContent = formGap > 10
    ? `${homeName}近期状态明显更佳，${document.getElementById('homeAdvantage').checked ? '主场加成进一步扩大了优势。' : '但未计入主场优势。'}`
    : formGap < -10 ? `${awayName}近期状态更为出色，客队具备制造惊喜的能力。` : '双方近期状态接近，比赛可能由临场发挥与关键机会决定。';
}

document.getElementById('predictionForm').addEventListener('submit', (event) => {
  event.preventDefault();
  calculatePrediction();
  document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

document.getElementById('resetBtn').addEventListener('click', () => {
  Object.entries(defaults).forEach(([id, value]) => { document.getElementById(id).value = value; });
  document.getElementById('homeAdvantage').checked = true;
  metricIds.forEach((id) => syncRange(document.getElementById(id)));
  calculatePrediction();
});

calculatePrediction();
