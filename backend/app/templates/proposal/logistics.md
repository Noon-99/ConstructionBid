# Logistics & Protection

{{#if logistics}}
{{#each logistics}}
## {{title}}

{{#if quantity}}
- **Quantity:** {{quantity}} {{unit}}
{{/if}}
- **Total Cost:** {{total_cost_formatted}}
- **Basis:** {{basis}}

{{#if notes}}
*Note: {{notes}}*
{{/if}}

{{/each}}
{{else}}
*No logistics items specified.*
{{/if}}






