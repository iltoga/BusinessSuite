/**
 * @module products/product_form
 * @description Handles product form interactions including:
 *   - Dynamic task form management (add/remove)
 *   - Task form indexing and renaming
 *   - Default task values for visa products
 *   - Document validity synchronization
 *   - Sortable document selection with drag-and-drop reordering
 * @requires jQuery
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';

    /**
     * Initialize the product form functionality
     */
    function initProductForm() {
        // Add task button handler
        const addTaskBtn = document.getElementById('add-task');
        if (addTaskBtn) {
            addTaskBtn.addEventListener('click', handleAddTask, false);
        }

        // Remove task button handler (delegated event)
        $(document).on('click', '.remove-task-btn', handleRemoveTask);

        // Document validity synchronization
        const validityField = document.getElementById('id_validity');
        if (validityField) {
            $(validityField).on('change', handleValidityChange);
        }

        // Initialize sortable document selectors
        initSortableSelects();
    }

    /**
     * Initialize sortable document selection widgets
     */
    function initSortableSelects() {
        document.querySelectorAll('.sortable-select-container').forEach(function(container) {
            const availableContainer = container.querySelector('.sortable-available');
            const selectedContainer = container.querySelector('.sortable-selected');
            const hiddenSelect = container.querySelector('.sortable-hidden-select');

            if (!availableContainer || !selectedContainer || !hiddenSelect) return;

            // Get ordered initial values from data attribute
            const orderedInitial = (container.dataset.orderedInitial || '').split(',').filter(Boolean);

            // Populate selected items from hidden select options
            if (orderedInitial.length > 0) {
                // Use ordered_initial to determine order
                orderedInitial.forEach(function(value, index) {
                    const option = hiddenSelect.querySelector('option[value="' + value + '"]');
                    if (option && option.selected) {
                        const label = option.dataset.label || option.textContent;
                        const selectedItem = createSelectedItem(value, label, index + 1);
                        selectedContainer.appendChild(selectedItem);

                        // Remove from available list
                        const availableItem = availableContainer.querySelector('.available-item[data-value="' + value + '"]');
                        if (availableItem) {
                            availableItem.remove();
                        }
                    }
                });
            } else {
                // Fallback: use hidden select order
                let orderNum = 1;
                Array.from(hiddenSelect.options).forEach(function(option) {
                    if (option.selected) {
                        const label = option.dataset.label || option.textContent;
                        const selectedItem = createSelectedItem(option.value, label, orderNum++);
                        selectedContainer.appendChild(selectedItem);

                        // Remove from available list
                        const availableItem = availableContainer.querySelector('.available-item[data-value="' + option.value + '"]');
                        if (availableItem) {
                            availableItem.remove();
                        }
                    }
                });
            }

            // Add item button click
            container.addEventListener('click', function(e) {
                if (e.target.closest('.add-item-btn')) {
                    const item = e.target.closest('.sortable-item');
                    if (item) {
                        addItemToSelected(item, availableContainer, selectedContainer, hiddenSelect);
                    }
                }

                if (e.target.closest('.remove-item-btn')) {
                    const item = e.target.closest('.sortable-item');
                    if (item) {
                        removeItemFromSelected(item, availableContainer, selectedContainer, hiddenSelect);
                    }
                }
            });

            // Drag and drop for reordering
            let draggedItem = null;

            selectedContainer.addEventListener('dragstart', function(e) {
                if (e.target.classList.contains('selected-item')) {
                    draggedItem = e.target;
                    e.target.style.opacity = '0.5';
                    e.dataTransfer.effectAllowed = 'move';
                }
            });

            selectedContainer.addEventListener('dragend', function(e) {
                if (e.target.classList.contains('selected-item')) {
                    e.target.style.opacity = '1';
                    draggedItem = null;
                    document.querySelectorAll('.selected-item').forEach(function(item) {
                        item.classList.remove('drag-over');
                    });
                    updateOrderNumbers(selectedContainer);
                    syncHiddenSelect(selectedContainer, hiddenSelect);
                }
            });

            selectedContainer.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                const targetItem = e.target.closest('.selected-item');
                if (targetItem && targetItem !== draggedItem) {
                    document.querySelectorAll('.selected-item').forEach(function(item) {
                        item.classList.remove('drag-over');
                    });
                    targetItem.classList.add('drag-over');
                }
            });

            selectedContainer.addEventListener('drop', function(e) {
                e.preventDefault();
                const targetItem = e.target.closest('.selected-item');
                if (targetItem && draggedItem && targetItem !== draggedItem) {
                    const rect = targetItem.getBoundingClientRect();
                    const midpoint = rect.top + rect.height / 2;
                    if (e.clientY < midpoint) {
                        selectedContainer.insertBefore(draggedItem, targetItem);
                    } else {
                        selectedContainer.insertBefore(draggedItem, targetItem.nextSibling);
                    }
                }
            });
        });
    }

    /**
     * Create a selected item element
     */
    function createSelectedItem(value, label, orderNum) {
        const selectedItem = document.createElement('div');
        selectedItem.className = 'sortable-item selected-item d-flex align-items-center p-2 mb-1 bg-primary-subtle rounded';
        selectedItem.dataset.value = value;
        selectedItem.dataset.label = label;
        selectedItem.draggable = true;
        selectedItem.style.cursor = 'grab';
        selectedItem.innerHTML = `
            <i class="bi bi-grip-vertical me-2 text-muted"></i>
            <span class="sortable-order-number badge bg-secondary me-2">${orderNum}</span>
            <span class="flex-grow-1">${label}</span>
            <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" title="Remove">
                <i class="bi bi-x"></i>
            </button>
        `;
        return selectedItem;
    }

    /**
     * Add an item from available to selected
     */
    function addItemToSelected(item, availableContainer, selectedContainer, hiddenSelect) {
        const value = item.dataset.value;
        const label = item.dataset.label;
        const orderNum = selectedContainer.querySelectorAll('.selected-item').length + 1;

        // Create selected item using helper
        const selectedItem = createSelectedItem(value, label, orderNum);
        selectedContainer.appendChild(selectedItem);
        item.remove();

        // Update hidden select
        syncHiddenSelect(selectedContainer, hiddenSelect);
    }

    /**
     * Remove an item from selected back to available
     */
    function removeItemFromSelected(item, availableContainer, selectedContainer, hiddenSelect) {
        const value = item.dataset.value;
        const label = item.dataset.label;

        // Create available item
        const availableItem = document.createElement('div');
        availableItem.className = 'sortable-item available-item d-flex align-items-center p-2 mb-1 bg-light rounded';
        availableItem.dataset.value = value;
        availableItem.dataset.label = label;
        availableItem.style.cursor = 'pointer';
        availableItem.innerHTML = `
            <span class="flex-grow-1">${label}</span>
            <button type="button" class="btn btn-sm btn-outline-primary add-item-btn" title="Add">
                <i class="bi bi-plus"></i>
            </button>
        `;

        // Insert in alphabetical order
        const existingItems = Array.from(availableContainer.querySelectorAll('.available-item'));
        let inserted = false;
        for (const existingItem of existingItems) {
            if (label.localeCompare(existingItem.dataset.label) < 0) {
                availableContainer.insertBefore(availableItem, existingItem);
                inserted = true;
                break;
            }
        }
        if (!inserted) {
            availableContainer.appendChild(availableItem);
        }

        item.remove();

        // Update order numbers and hidden select
        updateOrderNumbers(selectedContainer);
        syncHiddenSelect(selectedContainer, hiddenSelect);
    }

    /**
     * Update order numbers in the selected container
     */
    function updateOrderNumbers(selectedContainer) {
        selectedContainer.querySelectorAll('.selected-item').forEach(function(item, index) {
            const orderSpan = item.querySelector('.sortable-order-number');
            if (orderSpan) {
                orderSpan.textContent = index + 1;
            }
        });
    }

    /**
     * Sync the hidden select element with the current order
     */
    function syncHiddenSelect(selectedContainer, hiddenSelect) {
        // Deselect all options first
        Array.from(hiddenSelect.options).forEach(function(option) {
            option.selected = false;
        });

        // Get ordered values from selected container
        const orderedValues = [];
        selectedContainer.querySelectorAll('.selected-item').forEach(function(item) {
            orderedValues.push(item.dataset.value);
        });

        // Reorder options in hidden select to match the drag order
        // and select the ones that are in orderedValues
        const fragment = document.createDocumentFragment();
        const allOptions = Array.from(hiddenSelect.options);

        // First add selected options in order
        orderedValues.forEach(function(value) {
            const option = allOptions.find(opt => opt.value === value);
            if (option) {
                option.selected = true;
                fragment.appendChild(option);
            }
        });

        // Then add remaining unselected options
        allOptions.forEach(function(option) {
            if (!orderedValues.includes(option.value)) {
                fragment.appendChild(option);
            }
        });

        // Replace all options
        hiddenSelect.innerHTML = '';
        hiddenSelect.appendChild(fragment);
    }

    /**
     * Handle adding a new task form
     */
    function handleAddTask() {
        const formIdx = $('#id_tasks-TOTAL_FORMS').val();
        const emptyFormHtml = $('#empty-form').html();
        const newTaskForm = emptyFormHtml.replace(/__prefix__/g, formIdx);

        $('#task-form-list').append(newTaskForm);
        $('#id_tasks-TOTAL_FORMS').val(parseInt(formIdx) + 1);
        $('#id_tasks-' + formIdx + '-step').val(parseInt(formIdx) + 1);

        // If product type is 'visa', set default values for the first task form
        const productType = $('#id_product_type').val();
        if (productType === 'visa' && formIdx === '0') {
            $('#id_tasks-' + formIdx + '-name').val('Document Collection');
            $('#id_tasks-' + formIdx + '-description').val('Collecting documents from Customer');
        }
    }

    /**
     * Handle removing a task form
     */
    function handleRemoveTask() {
        if ($('.task-form').length > 1) {
            $(this).parent().remove();
            updateTaskFormIndices();
        }
    }

    /**
     * Update task form indices after removal
     */
    function updateTaskFormIndices() {
        const forms = $('#task-form-list .task-form');
        $('#id_tasks-TOTAL_FORMS').val(forms.length);

        let i = 0;
        for (const form of forms.toArray()) {
            $(form).find('input,select,checkbox').each(function() {
                const nameAttr = $(this).attr('name');
                const idAttr = $(this).attr('id');

                if (nameAttr) {
                    $(this).attr('name', nameAttr.replace(/-\d+-/, '-' + i + '-'));
                }
                if (idAttr) {
                    $(this).attr('id', idAttr.replace(/-\d+-/, '-' + i + '-'));
                }
            });
            i++;
        }
    }

    /**
     * Handle validity field change - sync with documents_min_validity
     */
    function handleValidityChange() {
        const validityValue = $(this).val();
        $('#id_documents_min_validity').val(validityValue);
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initProductForm);
    } else {
        initProductForm();
    }
})();
