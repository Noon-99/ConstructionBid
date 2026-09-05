# Payment Schedule

{{#if payment_schedule}}
{{#each payment_schedule}}
## {{title}}

- **Percentage:** {{percentage}}%
- **Amount:** {{amount_formatted}}
- **Trigger:** {{trigger}}

{{/each}}
{{else}}
*Payment schedule to be determined based on project milestones and contract terms.*
{{/if}}






