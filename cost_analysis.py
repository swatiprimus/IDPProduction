#!/usr/bin/env python3
# AWS Pricing (as of Dec 2024)
TEXTRACT_PRICE = 0.0015  # per page
CLAUDE_INPUT_PRICE = 0.003  # per 1K tokens
CLAUDE_OUTPUT_PRICE = 0.015  # per 1K tokens

# Assumptions
AVG_PAGE_COUNT = 10
AVG_INPUT_TOKENS_PER_PAGE = 3000  # OCR text + prompt
AVG_OUTPUT_TOKENS_PER_PAGE = 800   # Extracted data

print('='*80)
print('COST & PERFORMANCE ANALYSIS: Current vs Optimized')
print('='*80)
print()

# CURRENT IMPLEMENTATION
print('CURRENT IMPLEMENTATION (Page-by-Page)')
print('-'*80)

current_ocr_calls = 5  # Average pages needing OCR
current_llm_calls = 10  # 1 per page
current_input_tokens = current_llm_calls * AVG_INPUT_TOKENS_PER_PAGE
current_output_tokens = current_llm_calls * AVG_OUTPUT_TOKENS_PER_PAGE

current_ocr_cost = current_ocr_calls * TEXTRACT_PRICE
current_llm_input_cost = (current_input_tokens / 1000) * CLAUDE_INPUT_PRICE
current_llm_output_cost = (current_output_tokens / 1000) * CLAUDE_OUTPUT_PRICE
current_total_cost = current_ocr_cost + current_llm_input_cost + current_llm_output_cost

print(f'OCR Calls:              {current_ocr_calls} pages')
print(f'  Cost:                 ${current_ocr_cost:.4f}')
print()
print(f'LLM Calls:              {current_llm_calls} calls')
print(f'  Input Tokens:         {current_input_tokens:,} tokens')
print(f'  Input Cost:           ${current_llm_input_cost:.4f}')
print(f'  Output Tokens:        {current_output_tokens:,} tokens')
print(f'  Output Cost:          ${current_llm_output_cost:.4f}')
print()
print(f'TOTAL COST PER DOC:     ${current_total_cost:.4f}')
print(f'Processing Time:        45-60 seconds')
print()
print()

# PHASE 1: Batch Processing (2-3 pages per call)
print('PHASE 1: Batch Processing (2-3 pages/call)')
print('-'*80)

phase1_ocr_calls = 5  # Same OCR
phase1_llm_calls = 4  # 10 pages -> 4 batches (avg 2.5 pages per call)
phase1_input_tokens = int(phase1_llm_calls * AVG_INPUT_TOKENS_PER_PAGE * 2.5)
phase1_output_tokens = int(phase1_llm_calls * AVG_OUTPUT_TOKENS_PER_PAGE * 2.5)

phase1_ocr_cost = phase1_ocr_calls * TEXTRACT_PRICE
phase1_llm_input_cost = (phase1_input_tokens / 1000) * CLAUDE_INPUT_PRICE
phase1_llm_output_cost = (phase1_output_tokens / 1000) * CLAUDE_OUTPUT_PRICE
phase1_total_cost = phase1_ocr_cost + phase1_llm_input_cost + phase1_llm_output_cost

phase1_cost_savings = current_total_cost - phase1_total_cost
phase1_cost_savings_pct = (phase1_cost_savings / current_total_cost) * 100

print(f'OCR Calls:              {phase1_ocr_calls} pages')
print(f'  Cost:                 ${phase1_ocr_cost:.4f}')
print()
print(f'LLM Calls:              {phase1_llm_calls} calls (2-3 pages/call)')
print(f'  Input Tokens:         {phase1_input_tokens:,} tokens')
print(f'  Input Cost:           ${phase1_llm_input_cost:.4f}')
print(f'  Output Tokens:        {phase1_output_tokens:,} tokens')
print(f'  Output Cost:          ${phase1_llm_output_cost:.4f}')
print()
print(f'TOTAL COST PER DOC:     ${phase1_total_cost:.4f}')
print(f'Cost Savings:           ${phase1_cost_savings:.4f} ({phase1_cost_savings_pct:.1f}%)')
print(f'Processing Time:        25-35 seconds (40% faster)')
print()
print()

# PHASE 1+2: Smart OCR + Batch Processing
print('PHASE 1+2: Smart OCR + Batch Processing')
print('-'*80)

phase2_ocr_calls = 1  # Smart OCR: only 1-2 pages need it
phase2_llm_calls = 4  # Same as Phase 1
phase2_input_tokens = int(phase2_llm_calls * AVG_INPUT_TOKENS_PER_PAGE * 2.5)
phase2_output_tokens = int(phase2_llm_calls * AVG_OUTPUT_TOKENS_PER_PAGE * 2.5)

phase2_ocr_cost = phase2_ocr_calls * TEXTRACT_PRICE
phase2_llm_input_cost = (phase2_input_tokens / 1000) * CLAUDE_INPUT_PRICE
phase2_llm_output_cost = (phase2_output_tokens / 1000) * CLAUDE_OUTPUT_PRICE
phase2_total_cost = phase2_ocr_cost + phase2_llm_input_cost + phase2_llm_output_cost

phase2_cost_savings = current_total_cost - phase2_total_cost
phase2_cost_savings_pct = (phase2_cost_savings / current_total_cost) * 100

print(f'OCR Calls:              {phase2_ocr_calls} pages (Smart threshold)')
print(f'  Cost:                 ${phase2_ocr_cost:.4f}')
print()
print(f'LLM Calls:              {phase2_llm_calls} calls (2-3 pages/call)')
print(f'  Input Tokens:         {phase2_input_tokens:,} tokens')
print(f'  Input Cost:           ${phase2_llm_input_cost:.4f}')
print(f'  Output Tokens:        {phase2_output_tokens:,} tokens')
print(f'  Output Cost:          ${phase2_llm_output_cost:.4f}')
print()
print(f'TOTAL COST PER DOC:     ${phase2_total_cost:.4f}')
print(f'Cost Savings:           ${phase2_cost_savings:.4f} ({phase2_cost_savings_pct:.1f}%)')
print(f'Processing Time:        15-20 seconds (65% faster)')
print()
print()

# PHASE 1+2+3: Add Parallel Processing
print('PHASE 1+2+3: + Parallel Processing (3 concurrent)')
print('-'*80)

phase3_ocr_calls = 1
phase3_llm_calls = 4
phase3_input_tokens = phase2_input_tokens
phase3_output_tokens = phase2_output_tokens

phase3_ocr_cost = phase2_ocr_cost
phase3_llm_input_cost = phase2_llm_input_cost
phase3_llm_output_cost = phase2_llm_output_cost
phase3_total_cost = phase2_total_cost

phase3_cost_savings = current_total_cost - phase3_total_cost
phase3_cost_savings_pct = (phase3_cost_savings / current_total_cost) * 100

print(f'OCR Calls:              {phase3_ocr_calls} pages')
print(f'  Cost:                 ${phase3_ocr_cost:.4f}')
print()
print(f'LLM Calls:              {phase3_llm_calls} calls (parallel, 3 concurrent)')
print(f'  Input Tokens:         {phase3_input_tokens:,} tokens')
print(f'  Input Cost:           ${phase3_llm_input_cost:.4f}')
print(f'  Output Tokens:        {phase3_output_tokens:,} tokens')
print(f'  Output Cost:          ${phase3_llm_output_cost:.4f}')
print()
print(f'TOTAL COST PER DOC:     ${phase3_total_cost:.4f}')
print(f'Cost Savings:           ${phase3_cost_savings:.4f} ({phase3_cost_savings_pct:.1f}%)')
print(f'Processing Time:        8-12 seconds (80% faster)')
print()
print()

# PHASE 1+2+3+4: Add Regex-First Extraction
print('PHASE 1+2+3+4: + Regex-First Extraction')
print('-'*80)

phase4_ocr_calls = 1
phase4_llm_calls = 4
phase4_input_tokens = int(phase2_input_tokens * 0.75)  # 25% fewer tokens
phase4_output_tokens = int(phase2_output_tokens * 0.75)

phase4_ocr_cost = phase4_ocr_calls * TEXTRACT_PRICE
phase4_llm_input_cost = (phase4_input_tokens / 1000) * CLAUDE_INPUT_PRICE
phase4_llm_output_cost = (phase4_output_tokens / 1000) * CLAUDE_OUTPUT_PRICE
phase4_total_cost = phase4_ocr_cost + phase4_llm_input_cost + phase4_llm_output_cost

phase4_cost_savings = current_total_cost - phase4_total_cost
phase4_cost_savings_pct = (phase4_cost_savings / current_total_cost) * 100

print(f'OCR Calls:              {phase4_ocr_calls} pages')
print(f'  Cost:                 ${phase4_ocr_cost:.4f}')
print()
print(f'LLM Calls:              {phase4_llm_calls} calls (25% fewer tokens)')
print(f'  Input Tokens:         {phase4_input_tokens:,} tokens')
print(f'  Input Cost:           ${phase4_llm_input_cost:.4f}')
print(f'  Output Tokens:        {phase4_output_tokens:,} tokens')
print(f'  Output Cost:          ${phase4_llm_output_cost:.4f}')
print()
print(f'TOTAL COST PER DOC:     ${phase4_total_cost:.4f}')
print(f'Cost Savings:           ${phase4_cost_savings:.4f} ({phase4_cost_savings_pct:.1f}%)')
print(f'Processing Time:        8-12 seconds (80% faster)')
print()
print()

# SUMMARY TABLE
print('='*80)
print('SUMMARY: Cost & Performance Comparison')
print('='*80)
print()

print(f'{"Implementation":<25} {"Cost/Doc":<15} {"Cost %":<10} {"Time":<15} {"Speed Gain":<10}')
print('-'*80)
print(f'{"Current":<25} ${current_total_cost:<14.4f} {"100%":<10} {"45-60s":<15} {"100%":<10}')
print(f'{"Phase 1 (Batch)":<25} ${phase1_total_cost:<14.4f} {f"{100-phase1_cost_savings_pct:.0f}%":<10} {"25-35s":<15} {"40%":<10}')
print(f'{"Phase 1+2 (Smart OCR)":<25} ${phase2_total_cost:<14.4f} {f"{100-phase2_cost_savings_pct:.0f}%":<10} {"15-20s":<15} {"65%":<10}')
print(f'{"Phase 1+2+3 (Parallel)":<25} ${phase3_total_cost:<14.4f} {f"{100-phase3_cost_savings_pct:.0f}%":<10} {"8-12s":<15} {"80%":<10}')
print(f'{"Phase 1+2+3+4 (Regex)":<25} ${phase4_total_cost:<14.4f} {f"{100-phase4_cost_savings_pct:.0f}%":<10} {"8-12s":<15} {"80%":<10}')

print()
print()

# ANNUAL SAVINGS CALCULATION
print('='*80)
print('ANNUAL SAVINGS (Based on 1000 documents/month)')
print('='*80)
print()

docs_per_month = 1000
docs_per_year = docs_per_month * 12

current_annual = current_total_cost * docs_per_year
phase1_annual = phase1_total_cost * docs_per_year
phase2_annual = phase2_total_cost * docs_per_year
phase4_annual = phase4_total_cost * docs_per_year

print(f'Documents/Month:        {docs_per_month:,}')
print(f'Documents/Year:         {docs_per_year:,}')
print()
print(f'Current Annual Cost:    ${current_annual:,.2f}')
print(f'Phase 1 Annual Cost:    ${phase1_annual:,.2f}  (Save ${current_annual - phase1_annual:,.2f}/year)')
print(f'Phase 1+2 Annual Cost:  ${phase2_annual:,.2f}  (Save ${current_annual - phase2_annual:,.2f}/year)')
print(f'Phase 1+2+3+4 Annual:   ${phase4_annual:,.2f}  (Save ${current_annual - phase4_annual:,.2f}/year)')
print()
print()

# PERFORMANCE GAINS
print('='*80)
print('PERFORMANCE GAINS')
print('='*80)
print()

current_time_min = 45
current_time_max = 60
phase4_time_min = 8
phase4_time_max = 12

time_saved_min = current_time_min - phase4_time_max
time_saved_max = current_time_max - phase4_time_min
time_saved_pct = ((current_time_max - phase4_time_max) / current_time_max) * 100

print(f'Current Processing:     {current_time_min}-{current_time_max} seconds')
print(f'Optimized Processing:   {phase4_time_min}-{phase4_time_max} seconds')
print(f'Time Saved:             {time_saved_min}-{time_saved_max} seconds ({time_saved_pct:.0f}% faster)')
print()

# Throughput improvement
current_throughput = 3600 / current_time_max  # docs per hour
optimized_throughput = 3600 / phase4_time_max
throughput_gain = optimized_throughput / current_throughput

print(f'Current Throughput:     {current_throughput:.0f} docs/hour')
print(f'Optimized Throughput:   {optimized_throughput:.0f} docs/hour')
print(f'Throughput Gain:        {throughput_gain:.1f}x faster')
print()
print()

# ROI CALCULATION
print('='*80)
print('IMPLEMENTATION ROI')
print('='*80)
print()

implementation_cost = 2000  # Estimated dev time
annual_savings = current_annual - phase4_annual
roi_months = (implementation_cost / annual_savings) * 12

print(f'Estimated Implementation Cost:  ${implementation_cost:,.2f}')
print(f'Annual Savings:                 ${annual_savings:,.2f}')
print(f'ROI Payback Period:             {roi_months:.1f} months')
print(f'Year 1 Net Savings:             ${annual_savings - implementation_cost:,.2f}')
print()
