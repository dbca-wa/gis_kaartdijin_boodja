import { defineStore } from "pinia";
import { Attribute } from "../providers/relatedEntityProvider.api";
import { ref, Ref } from "vue";
import { AttributeCrudType } from "./AttributeStore.api";

export const useAttributeStore = defineStore("attribute",  () => {
  const attributes: Ref<Attribute[]> = ref([]);
  const editingAttribute: Ref<Partial<Attribute> | undefined> = ref(undefined);
  const attributeCrudType: Ref<AttributeCrudType> = ref(AttributeCrudType.None);

  function setAttributes (newAttributes: Array<Attribute>) {
    attributes.value = newAttributes;
  }

  function setEditingAttribute(attribute: Partial<Attribute>) {
    editingAttribute.value = attribute;
  }

  function updateAttribute (attribute: Attribute) {
    if (!attributes.value.find(value => value.id === attribute.id)) {
      throw new Error(`\`updateAttribute\`: Tried to update non-existent attribute: ${JSON.stringify(attribute)}`);
    }

    attributes.value = attributes.value.map(value => value.id === attribute.id ? attribute : value);
  }

  function addAttribute (attribute: Attribute) {
    attributes.value = [...attributes.value, attribute];
  }

  function removeAttribute (id: number) {
    if (!attributes.value.find(value => value.id === id)) {
      throw new Error(`\`removeAttribute\`: Tried to delete non-existent attribute: ${id}`);
    }

    attributes.value = attributes.value.filter(value => value.id !== id);
  }

  return { attributes, editingAttribute, attributeCrudType, setEditingAttribute, setAttributes, updateAttribute, addAttribute,
    removeAttribute };
});
