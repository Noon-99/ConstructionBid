# Permits & Inspections

{{#if permits_and_inspections}}
{{#each permits_and_inspections}}
## {{title}}

- **Total Cost:** {{total_cost_formatted}}
- **Basis:** {{basis}}

{{#if notes}}
*Note: {{notes}}*
{{/if}}

{{/each}}
{{else}}
*Permits and inspections costs to be determined based on local requirements and project scope.*
{{/if}}






