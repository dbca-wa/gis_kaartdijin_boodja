<script lang="ts" setup>
  import { CatalogueEntry } from "../../providers/catalogueEntryProvider.api";
  import Accordion from "../widgets/Accordion.vue";
  import FormInput from "../widgets/FormInput.vue";
  import FormTextarea from "../widgets/FormTextarea.vue";
  import NotificationsCard from "../widgets/NotificationsCard.vue";

  defineProps<{
    entry: CatalogueEntry
  }>();
</script>

<template>
  <accordion id-prefix="details" header-text="Details" class="mt-4">
    <template #body>
      <div class="form d-flex gap-3 flex-column">
        <form-input field="name" name="Name" :value="entry?.name" type="text" :readonly="true"/>
        <form-input field="custodian" name="Custodian" :value="entry?.custodian?.username" type="text"
                    :readonly="true"/>
      </div>
    </template>
  </accordion>
  <accordion id-prefix="description" header-text="Description" class="mt-4">
    <template #body>
      <div class="form d-flex gap-3 flex-column">
        <form-textarea field="description" name="Description" :value="entry?.description" :readonly="true"/>
      </div>
    </template>
  </accordion>
  <notifications-card/>
</template>