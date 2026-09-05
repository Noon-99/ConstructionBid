# Scope of Work

{{#if sections}}
{{#each sections}}
## {{title}}

{{#if division}}
**Division:** {{division}}
{{/if}}

{{#if line_items}}
| Description | Quantity | Unit | Unit Cost | Total |
|------------|----------|------|-----------|-------|
{{#each line_items}}
| {{title}} | {{quantity_display}} | {{unit_display}} | {{unit_cost_display}} | {{total_cost_formatted}} |
{{#if notes}}
| *{{notes}}* | | | | |
{{/if}}
{{/each}}

**Subtotal:** {{subtotal_formatted}}
{{/if}}

---
{{/each}}
{{else}}
*No detailed scope sections available.*
{{/if}}

