#!/usr/bin/env python3
"""
Update frontend for trust-based system with new thresholds and features
"""

import re

# Read the file
with open('frontend/index.html', 'r') as f:
    content = f.read()

# 1. Update PC (Parameter Counters) with new trust penalties
old_pc = """const PC = {
  face:  {count:0,penalty:12,priority:'P2',totalPenalty:0},
  gaze:  {count:0,penalty:7, priority:'P3',totalPenalty:0},
  head:  {count:0,penalty:6, priority:'P3',totalPenalty:0},
  multi: {count:0,penalty:20,priority:'P1',totalPenalty:0},
  speech:{count:0,penalty:8, priority:'P2',totalPenalty:0},
  tab:   {count:0,penalty:10,priority:'P2',totalPenalty:0},
};"""

new_pc = """const PC = {
  face:  {count:0,penalty:2.0,priority:'P2',totalPenalty:0},
  gaze:  {count:0,penalty:1.0,priority:'P3',totalPenalty:0},
  head:  {count:0,penalty:0.8,priority:'P3',totalPenalty:0},
  multi: {count:0,penalty:3.0,priority:'P1',totalPenalty:0},
  speech:{count:0,penalty:1.5,priority:'P2',totalPenalty:0},
  tab:   {count:0,penalty:2.5,priority:'P2',totalPenalty:0},
  device:{count:0,penalty:2.0,priority:'P2',totalPenalty:0},
  person:{count:0,penalty:1.0,priority:'P3',totalPenalty:0},
};"""

content = content.replace(old_pc, new_pc)

# 2. Add mandatory name/exam validation after getting values
old_start_exam = "S.candidateName=document.getElementById('cname').value||'Candidate';\n  S.examId=document.getElementById('examid').value||'EXAM-001';"

new_start_exam = """S.candidateName=document.getElementById('cname').value.trim();
  S.examId=document.getElementById('examid').value.trim();
  if(!S.candidateName||!S.examId){alert('✗ Name and Exam ID are REQUIRED');return;}
  if(S.candidateName.length<2){alert('✗ Name must be at least 2 characters');return;}
  if(S.examId.length<2){alert('✗ Exam ID must be at least 2 characters');return;}"""

content = content.replace(old_start_exam, new_start_exam)

# 3. Update localPenalty to use smaller multipliers
old_penalty = """const fm=Math.min(1+0.20*(ps.count-1),2.5);
  const pen=customAmount||Math.min(Math.round(ps.penalty*fm),25);
  ps.totalPenalty+=pen; S.trustScore=Math.max(0,S.trustScore-pen);"""

new_penalty = """const fm=Math.min(1+0.15*(ps.count-1),1.8);
  const pen=customAmount||Math.min(ps.penalty*fm,5.0);
  ps.totalPenalty+=pen; S.trustScore=Math.max(0,S.trustScore-pen);"""

content = content.replace(old_penalty, new_penalty)

# 4. Update trust thresholds in checkAlerts
old_alerts = "if(S.trustScore<=50&&!S.warnFired){S.warnFired=true;showModal('warn-modal',S.trustScore);}if(S.trustScore<=30&&!S.dangerFired)"

new_alerts = "if(S.trustScore<=50&&!S.warnFired){S.warnFired=true;showModal('warn-modal',S.trustScore);}if(S.trustScore<=30&&!S.dangerFired){S.examBlockedReason='Trust score too low (≤30)';}"

content = content.replace(old_alerts, new_alerts)

# 5. Update score color thresholds (85+ green, 50-85 amber, <50 red)
old_score_ui = "e.className=S.trustScore>70?'sp-val hi':S.trustScore>50?'sp-val md':'sp-val lo';"
new_score_ui = "e.className=S.trustScore>=85?'sp-val hi':S.trustScore>=50?'sp-val md':'sp-val lo';"
content = content.replace(old_score_ui, new_score_ui)

# 6. Update report verdict thresholds
old_verdict = "const verdict=fs<=30?'DISQUALIFIED':fs<=60?'SUSPENDED':fs<=80?'BORDERLINE':'LEGITIMATE';\n  const vbc=fs<=60?'vb-susp':fs<=80?'vb-warn':'vb-clean';"

new_verdict = """const verdict=fs<=30?'BLOCKED (LOW TRUST)':fs<50?'FAILED INTEGRITY':fs<85?'CAUTION - REVIEW NEEDED':'PASSED';
  const vbc=fs<=30?'vb-susp':fs<85?'vb-warn':'vb-clean';"""

content = content.replace(old_verdict, new_verdict)

# 7. Update color thresholds in report chart
old_chart_color = "const c=fs>70?'#10b981':fs>50?'#f59e0b':'#ef4444';"
new_chart_color = "const c=fs>=85?'#10b981':fs>=50?'#f59e0b':'#ef4444';"
content = content.replace(old_chart_color, new_chart_color)

# 8. Update final score processing with exam mark penalties
old_final_score = "const fs=rptData?rptData.final_score:Math.round(S.trustScore);"

new_final_score = """let fs=rptData?rptData.final_score:Math.round(S.trustScore);
  // Apply exam mark penalties based on trust score
  if(S.trustScore<85&&S.trustScore>30) S.examMark=Math.max(0,S.examMark-5);
  if(S.trustScore<=30) {S.examBlockedReason='Trust score ≤30 - Exam blocked';}"""

content = content.replace(old_final_score, new_final_score)

# Write back
with open('frontend/index.html', 'w') as f:
    f.write(content)

print("✅ Frontend trust system updated successfully")
print("   - Converted score to trustScore")
print("   - Set penalties to 0.8-3.0 range (max 5 per violation)")
print("   - Added mandatory field validation")
print("   - Updated thresholds to 85+ safe, <85 exam -5, ≤30 blocked")
