// Modern JS to replace Bootstrap functionality
document.addEventListener('DOMContentLoaded', function() {
  // Dropdown functionality
  document.querySelectorAll('.dropdown-toggle').forEach(function(element) {
    element.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      
      // Close all other dropdowns
      document.querySelectorAll('.dropdown-menu.show').forEach(function(menu) {
        if (!menu.parentNode.contains(element)) {
          menu.classList.remove('show');
        }
      });
      
      // Toggle current dropdown
      const dropdownMenu = this.parentNode.querySelector('.dropdown-menu');
      if (dropdownMenu) {
        dropdownMenu.classList.toggle('show');
      }
    });
  });
  
  // Close dropdowns when clicking outside
  document.addEventListener('click', function(e) {
    if (!e.target.matches('.dropdown-toggle') && !e.target.closest('.dropdown-menu')) {
      document.querySelectorAll('.dropdown-menu.show').forEach(function(element) {
        element.classList.remove('show');
      });
    }
  });
  
  // Convert btn-group to dropdown
  document.querySelectorAll('.btn-group').forEach(function(group) {
    group.classList.add('dropdown');
  });
  
  // 实现拖拽功能以替代左右箭头
  setupDragAndDrop();
  
  // Smooth animations for panels
  document.querySelectorAll('.panel').forEach(function(panel) {
    panel.addEventListener('mouseenter', function() {
      this.style.transform = 'translateY(-4px)';
      this.style.boxShadow = '0 10px 20px rgba(0, 0, 0, 0.08)';
    });
    
    panel.addEventListener('mouseleave', function() {
      this.style.transform = 'translateY(0)';
      this.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.05)';
    });
  });
  
  // Enhance button hover effects
  document.querySelectorAll('.btn').forEach(function(btn) {
    btn.addEventListener('mouseenter', function() {
      this.style.transform = 'translateY(-1px)';
    });
    
    btn.addEventListener('mouseleave', function() {
      this.style.transform = 'translateY(0)';
    });
  });
  
  // Add ripple effect to buttons
  function createRipple(event) {
    const button = event.currentTarget;
    
    const circle = document.createElement('span');
    const diameter = Math.max(button.clientWidth, button.clientHeight);
    const radius = diameter / 2;
    
    circle.style.width = circle.style.height = `${diameter}px`;
    circle.style.left = `${event.clientX - button.getBoundingClientRect().left - radius}px`;
    circle.style.top = `${event.clientY - button.getBoundingClientRect().top - radius}px`;
    circle.classList.add('ripple');
    
    const ripple = button.querySelector('.ripple');
    if (ripple) {
      ripple.remove();
    }
    
    button.appendChild(circle);
  }
  
  document.querySelectorAll('.btn, .label').forEach(function(button) {
    button.style.position = 'relative';
    button.style.overflow = 'hidden';
    button.addEventListener('click', createRipple);
  });
  
  // Add CSS for ripple effect
  const style = document.createElement('style');
  style.textContent = `
    .ripple {
      position: absolute;
      background-color: rgba(255, 255, 255, 0.3);
      border-radius: 50%;
      transform: scale(0);
      animation: ripple 0.6s linear;
      pointer-events: none;
    }
    
    @keyframes ripple {
      to {
        transform: scale(4);
        opacity: 0;
      }
    }
  `;
  document.head.appendChild(style);
  
  // 设置拖拽功能
  function setupDragAndDrop() {
    const columnsContainer = document.getElementById('post-columns');
    if (!columnsContainer) return;
    
    // 添加拖拽手柄到所有的列标题
    document.querySelectorAll('.panel-heading').forEach(function(heading) {
      const dragHandle = document.createElement('div');
      dragHandle.className = 'drag-handle';
      dragHandle.innerHTML = '<i class="fas fa-grip-vertical"></i>';
      heading.insertBefore(dragHandle, heading.firstChild);
    });
    
    let draggedElement = null;
    let placeholder = null;
    let initialX = 0;
    let initialY = 0;
    let scrollInterval = null;
    
    // 开始拖拽
    columnsContainer.addEventListener('mousedown', function(e) {
      const handle = e.target.closest('.drag-handle');
      if (!handle) return;
      
      const column = e.target.closest('.column');
      if (!column) return;
      
      e.preventDefault();
      
      // 创建占位符
      placeholder = document.createElement('div');
      placeholder.className = 'column column-placeholder';
      placeholder.style.width = column.offsetWidth + 'px';
      placeholder.style.height = column.offsetHeight + 'px';
      
      // 初始化拖拽状态
      draggedElement = column;
      draggedElement.classList.add('dragging');
      
      // 记录初始位置
      const rect = draggedElement.getBoundingClientRect();
      initialX = e.clientX - rect.left;
      initialY = e.clientY - rect.top;
      
      // 设置拖拽元素的样式
      draggedElement.style.position = 'absolute';
      draggedElement.style.zIndex = 1000;
      updateDraggedPosition(e);
      
      // 插入占位符
      draggedElement.parentNode.insertBefore(placeholder, draggedElement);
      
      // 添加移动和释放事件
      document.addEventListener('mousemove', dragMove);
      document.addEventListener('mouseup', dragEnd);
    });
    
    // 拖拽过程
    function dragMove(e) {
      if (!draggedElement) return;
      
      updateDraggedPosition(e);
      
      // 处理页面滚动
      handleScroll(e);
      
      // 处理拖拽到新位置
      const columns = Array.from(columnsContainer.querySelectorAll('.column:not(.dragging):not(.column-placeholder)'));
      let nextColumn = null;
      
      // 查找合适的插入位置
      const draggedRect = draggedElement.getBoundingClientRect();
      const draggedCenterX = draggedRect.left + draggedRect.width / 2;
      const draggedCenterY = draggedRect.top + draggedRect.height / 2;
      
      // 查找最近的列
      let closestDistance = Infinity;
      let closestColumn = null;
      let insertBefore = true;
      
      for (const column of columns) {
        const rect = column.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        
        // 计算距离
        const dx = centerX - draggedCenterX;
        const dy = centerY - draggedCenterY;
        const distance = Math.sqrt(dx * dx + dy * dy);
        
        if (distance < closestDistance) {
          closestDistance = distance;
          closestColumn = column;
          // 如果拖拽元素在列的左侧或上方，则插入到该列之前，否则插入到该列之后
          insertBefore = (draggedCenterX < centerX || 
                         (draggedCenterX === centerX && draggedCenterY < centerY));
        }
      }
      
      // 移动占位符到新位置
      if (closestColumn) {
        if (insertBefore) {
          columnsContainer.insertBefore(placeholder, closestColumn);
        } else {
          const nextSibling = closestColumn.nextElementSibling;
          if (nextSibling) {
            columnsContainer.insertBefore(placeholder, nextSibling);
          } else {
            columnsContainer.appendChild(placeholder);
          }
        }
      } else if (columns.length > 0) {
        // 如果没有找到最近的列，但有其他列，则添加到末尾
        columnsContainer.appendChild(placeholder);
      }
    }
    
    // 处理页面滚动
    function handleScroll(e) {
      // 清除现有的滚动间隔
      if (scrollInterval) {
        clearInterval(scrollInterval);
        scrollInterval = null;
      }
      
      const scrollSpeed = 10; // 滚动速度
      const scrollTriggerDistance = 100; // 触发滚动的距离
      
      const windowHeight = window.innerHeight;
      const scrollY = window.scrollY;
      const maxScroll = document.body.scrollHeight - windowHeight;
      
      // 检查鼠标是否靠近屏幕顶部或底部
      if (e.clientY < scrollTriggerDistance) {
        // 向上滚动
        scrollInterval = setInterval(() => {
          window.scrollTo(0, Math.max(0, scrollY - scrollSpeed));
          updateDraggedPosition(e);
        }, 16);
      } else if (e.clientY > windowHeight - scrollTriggerDistance) {
        // 向下滚动
        scrollInterval = setInterval(() => {
          window.scrollTo(0, Math.min(maxScroll, scrollY + scrollSpeed));
          updateDraggedPosition(e);
        }, 16);
      }
    }
    
    // 结束拖拽
    function dragEnd(e) {
      if (!draggedElement) return;
      
      // 清除滚动定时器
      if (scrollInterval) {
        clearInterval(scrollInterval);
        scrollInterval = null;
      }
      
      // 恢复元素的样式
      draggedElement.style.position = '';
      draggedElement.style.top = '';
      draggedElement.style.left = '';
      draggedElement.style.width = '';
      draggedElement.style.height = '';
      draggedElement.style.zIndex = '';
      draggedElement.classList.remove('dragging');
      
      // 将元素移动到占位符的位置
      placeholder.parentNode.insertBefore(draggedElement, placeholder);
      placeholder.remove();
      
      // 获取元素的新位置
      const columns = Array.from(columnsContainer.querySelectorAll('.column'));
      const newPosition = columns.indexOf(draggedElement);
      const keywords = dlmonitor.getKeywords();
      
      // 重新排序关键词
      if (newPosition !== -1) {
        // 从原始数组获取关键词
        const originalIndex = parseInt(draggedElement.querySelector('[id^="column-title-"]').id.split('-').pop());
        const keyword = keywords[originalIndex];
        
        // 如果位置变化了，才进行处理
        if (originalIndex !== newPosition) {
          // 删除原始关键词
          keywords.splice(originalIndex, 1);
          
          // 插入到新位置
          keywords.splice(newPosition, 0, keyword);
          
          // 保存新排序到cookie
          Cookies.set("keywords", keywords.join(","));
          
          // 不重新请求数据，只更新DOM排序
          updateColumnIds(columns);
        }
      }
      
      // 清理
      draggedElement = null;
      
      // 移除事件监听器
      document.removeEventListener('mousemove', dragMove);
      document.removeEventListener('mouseup', dragEnd);
    }
    
    // 更新列的ID以匹配新的顺序
    function updateColumnIds(columns) {
      columns.forEach((column, index) => {
        const titleElement = column.querySelector('.panel-title');
        const closeButton = column.querySelector('[id^="close-btn-"]');
        const leftButton = column.querySelector('[id^="left-btn-"]');
        const rightButton = column.querySelector('[id^="right-btn-"]');
        const postsElement = column.querySelector('[id^="posts-"]');
        
        // 更新ID
        if (titleElement) titleElement.id = `column-title-${index}`;
        if (closeButton) closeButton.id = `close-btn-${index}`;
        if (leftButton) leftButton.id = `left-btn-${index}`;
        if (rightButton) rightButton.id = `right-btn-${index}`;
        if (postsElement) postsElement.id = `posts-${index}`;
        
        // 更新按钮的data-pos属性
        if (leftButton) leftButton.setAttribute('data-pos', index);
        if (rightButton) rightButton.setAttribute('data-pos', index);
      });
    }
    
    // 更新拖拽元素位置
    function updateDraggedPosition(e) {
      if (!draggedElement) return;
      
      const x = e.clientX - initialX;
      const y = e.clientY - initialY + window.scrollY; // 添加页面滚动偏移
      
      draggedElement.style.left = x + 'px';
      draggedElement.style.top = y + 'px';
    }
  }
}); 