# Project Schedule

{{#if schedule}}
{{#if schedule.estimated_start_date}}
**Estimated Start Date:** {{schedule.estimated_start_date}}
{{/if}}

{{#if schedule.estimated_duration_days}}
**Estimated Duration:** {{schedule.estimated_duration_days}} days (approximately {{estimated_duration_weeks}} weeks)
{{/if}}

{{#if schedule.estimated_completion_date}}
**Estimated Completion Date:** {{schedule.estimated_completion_date}}
{{/if}}
{{else}}
{{#if estimated_duration_weeks}}
**Estimated Duration:** {{estimated_duration_weeks}} weeks (derived from labor breakdown)
{{/if}}
{{/if}}

{{#unless schedule}}
{{#unless estimated_duration_weeks}}
*Project schedule to be determined based on site conditions and permit approvals.*
{{/unless}}
{{/unless}}






