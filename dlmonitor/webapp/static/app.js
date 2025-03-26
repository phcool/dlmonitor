/*
Javascript for Deep Community.
*/

INIT_KEYWORDS = "arxiv:large language model,nature:machine learning,github:llm";

// 常量定义      
DEFAULT_KEYWORDS = "arxiv:large language model,nature:machine learning,github:llm";

DATE_TOKEN_MAP = {
    'today': 0,  // 仅今天
    '2-days': 2,  // 最近两天
    '1-week': 7,
    '1-month': 31
}

dlmonitor = {
    ajaxCount: 0,
    previewTimeout: null,
    currentPlatform: 'arxiv',  // Default platform
    sortPreferences: {},  // 存储每个列的排序偏好
    activeDropdown: null  // 跟踪当前激活的下拉菜单
};

// 核心函数
dlmonitor.getKeywords = function() {
    var keywords = Cookies.get('keywords');
    if (keywords == undefined) {
        keywords = INIT_KEYWORDS;
    }
    return keywords ? keywords.split(",") : [];
};

// 初始化列的事件绑定
dlmonitor.initColumnEvents = function() {
    // 此函数已经不再需要，所有事件都通过事件委托处理
    // 保留此空函数以防有地方调用
    console.log("initColumnEvents被调用，但不执行任何操作");
};

// 处理下拉菜单
dlmonitor.setupDropdowns = function() {
    console.log("重新设置所有下拉菜单");
    
    // 清除现有的全局点击处理程序
    $(document).off('click.dropdown');
    
    // 点击页面任何地方关闭下拉菜单
    $(document).on('click.dropdown', function(e) {
        // 如果点击的是下拉按钮或菜单内容，则不在这里处理
        if ($(e.target).closest('.dropdown-btn, .dropdown-content, .sort-dropdown-btn, .dropdown-content a').length) {
            return;
        }
        
        // 关闭所有下拉菜单
        $('.dropdown-content').addClass('hidden');
        dlmonitor.activeDropdown = null;
        console.log("关闭所有下拉菜单 (点击外部区域)");
    });
    
    // 移除所有旧的事件处理程序
    $('.dropdown-btn').off('click');
    $('.dropdown-content a').off('click');
    $('.sort-dropdown-btn').off('click');
    $('.sort-option').off('click');
    
    // 平台选择下拉菜单 - 直接绑定到元素而不是通过委托
    $('#platform-dropdown-btn').on('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        var $dropdown = $('#platform-dropdown');
        var isVisible = !$dropdown.hasClass('hidden');
        
        // 关闭所有下拉菜单
        $('.dropdown-content').addClass('hidden');
        
        // 如果当前菜单已打开，则关闭它，否则打开它
        if (!isVisible) {
            $dropdown.removeClass('hidden');
            dlmonitor.activeDropdown = 'platform';
            console.log("打开平台选择下拉菜单");
        } else {
            dlmonitor.activeDropdown = null;
            console.log("关闭平台选择下拉菜单");
        }
    });
    
    // 平台选择处理 - 直接绑定
    $('#platform-dropdown a').on('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        var platform = $(this).data('platform');
        console.log("选择平台:", platform);
        dlmonitor.selectPlatform(platform);
        $('#platform-dropdown').addClass('hidden');
    });
    
    // 日期过滤下拉菜单 - 直接绑定
    $('#date-dropdown-btn').on('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        var $dropdown = $('#date-dropdown');
        var isVisible = !$dropdown.hasClass('hidden');
        
        // 关闭所有下拉菜单
        $('.dropdown-content').addClass('hidden');
        
        // 如果当前菜单已打开，则关闭它，否则打开它
        if (!isVisible) {
            $dropdown.removeClass('hidden');
            dlmonitor.activeDropdown = 'date';
            console.log("打开日期过滤下拉菜单");
        } else {
            dlmonitor.activeDropdown = null;
            console.log("关闭日期过滤下拉菜单");
        }
    });
    
    // 日期选择处理 - 直接绑定
    $('#date-dropdown a').on('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        var datetoken = $(this).data('datetoken');
        console.log("选择日期过滤:", datetoken);
        dlmonitor.filterDate(datetoken);
        $('#date-dropdown').addClass('hidden');
    });
    
    // 排序下拉菜单（使用事件委托，因为这些元素可能动态创建）
    $(document).off('click', '.sort-dropdown-btn');
    $(document).on('click', '.sort-dropdown-btn', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        var $container = $(this).closest('.sort-dropdown-container');
        var $dropdown = $container.find('.dropdown-content');
        var isVisible = !$dropdown.hasClass('hidden');
        
        // 关闭所有下拉菜单
        $('.dropdown-content').addClass('hidden');
        
        // 如果当前菜单已打开，则关闭它，否则打开它
        if (!isVisible) {
            $dropdown.removeClass('hidden');
            dlmonitor.activeDropdown = 'sort';
            console.log("打开排序下拉菜单");
        } else {
            dlmonitor.activeDropdown = null;
            console.log("关闭排序下拉菜单");
        }
    });
    
    // 确保菜单项点击有效（使用事件委托）
    $(document).off('click', '.sort-option');
    $(document).on('click', '.sort-option', function(e) {
        e.preventDefault();
        e.stopPropagation();
        var index = $(this).data('index');
        var sortType = $(this).data('sort');
        console.log("排序点击:", index, sortType);
        dlmonitor.sortColumn(index, sortType);
    });
    
    console.log("下拉菜单设置完成");
};

// 选择平台
dlmonitor.selectPlatform = function(platform) {
    dlmonitor.currentPlatform = platform;
    $("#platform-select").text(platform.charAt(0).toUpperCase() + platform.slice(1));
    
    // 检查是否需要刷新预览内容
    var text = $("#new-keyword").val();
    if (text.length >= 3 && $(".preview").is(":visible")) {
        console.log("平台更改，刷新预览:", platform, text);
        $("#preview-kw").html(platform + ":" + text);
        dlmonitor.fetch(platform, platform + ":" + text, 'preview');
    }
};

// 生成排序图标和文本
dlmonitor.getSortHtml = function(sortType) {
    // 直接返回首字母大写的排序类型，不添加图标
    return sortType.charAt(0).toUpperCase() + sortType.slice(1);
};

// 添加关键字
dlmonitor.addKeyword = function(w) {
    if (w == undefined || typeof(w) == "object" || !w) {
        w = $("#new-keyword").val()
    }
    if (w.length == 0) {
        return;
    }
    if (w.includes(",")) {
        alert("Keyword cannot include comma.");
        return;
    }
    if (w.length > 80) {
        alert("Keyword cannot be longer than 80 characters.")
        return;
    }
    
    // 检查是否已经包含平台前缀
    if (!w.includes(":")) {
        w = dlmonitor.currentPlatform + ":" + w;
    }
    
    $("#new-keyword").val("")
    var kwList = dlmonitor.getKeywords();
    if (kwList.length > 10) {
        alert("Please no more than 10 monitors.");
        return;
    }
    kwList.push(w.trim());
    var newKeywords = kwList.join(",");
    Cookies.set("keywords", newKeywords);
    dlmonitor.switchPreview(false);
    
    dlmonitor.showDate();
    
    // 获取新列的索引
    var newIndex = kwList.length - 1;
    
    // 添加新的列到DOM
    var template = $("#column-template").html();
    template = template.replace(/NUM/g, "" + newIndex);
    $("#post-columns").append(template);
    
    // 设置新列的标题和数据属性
    var kw = kwList[newIndex];
    $("#column-title-" + newIndex).html(kw);
    $("#close-btn-" + newIndex).data("keyword", kw);
    
    // 设置排序偏好
    var sortType = dlmonitor.getSortPreference(kw);
    $("#sort-info-" + newIndex).html(dlmonitor.getSortHtml(sortType));
    
    console.log("添加新列，索引:", newIndex, "关键字:", kw, "排序类型:", sortType);
    
    // 确保菜单数据属性被正确替换（双重检查）
    $(".column").last().find('.sort-option').each(function() {
        $(this).attr('data-index', newIndex);
    });
    
    // 为新添加的列加载数据
    var parts = w.split(":");
    if (parts.length === 2) {
        var src = parts[0];
        console.log("正在为新列加载数据:", src, w, newIndex, "排序类型:", sortType);
        dlmonitor.fetch(src, w, newIndex, 0, sortType);
        
        // 添加定时器检查加载状态
        setTimeout(function() {
            var columnContent = $("#posts-" + newIndex).html();
            if (columnContent && columnContent.indexOf("loader-large.gif") > -1) {
                console.log("列加载超时，正在重试...", newIndex);
                dlmonitor.fetch(src, w, newIndex, 0, sortType);
                
                setTimeout(function() {
                    columnContent = $("#posts-" + newIndex).html();
                    if (columnContent && columnContent.indexOf("loader-large.gif") > -1) {
                        $("#posts-" + newIndex).html(
                            "<div class='error-message'>数据加载超时。 " +
                            "<div class='btn-group'>" +
                            "<button class='btn btn-default retry-btn' data-src='" + src + "' data-keyword='" + w + "' data-index='" + newIndex + "'>重试</button>" +
                            "<button class='btn btn-primary refresh-btn' data-index='" + newIndex + "'>强制刷新</button>" +
                            "<button class='btn btn-warning' onclick='window.location.reload()'>重新加载页面</button>" +
                            "</div></div>"
                        );
                    }
                }, 5000);
            }
        }, 3000);
    }
};

// 移除关键字
dlmonitor.removeKeyword = function(e) {
    var w = $(e).data('keyword');
    if (w == undefined) {
        console.error("无法获取关键字数据");
        return;
    }
    
    var kwList = dlmonitor.getKeywords();
    var index = kwList.indexOf(w);
    if (index === -1) {
        console.error("找不到关键字:", w);
        return;
    }
    
    console.log("准备删除列:", index, "关键字:", w);
    
    // 从列表中移除关键字
    kwList.splice(index, 1);
    
    // 保存新的关键字列表到Cookie
    var newKeywords = kwList.join(",");
    Cookies.set("keywords", newKeywords);
    
    // 标记所有列以跟踪它们
    $(".post-columns .column").each(function(i) {
        $(this).attr("data-column-index", i);
    });
    
    // 移除特定列
    var columnToRemove = $(".post-columns .column[data-column-index='" + index + "']");
    if (columnToRemove.length === 0) {
        console.error("找不到要删除的列元素:", index);
        // 尝试重新布局
        dlmonitor.placeColumns();
        return;
    }
    
    // 安全地移除列
    columnToRemove.remove();
    console.log("已删除列:", index);
    
    // 获取剩余的列元素
    var remainingColumns = $(".post-columns .column");
    console.log("剩余列数:", remainingColumns.length, "应有列数:", kwList.length);
    
    if (remainingColumns.length !== kwList.length) {
        console.warn("列数不匹配，重新布局...");
        dlmonitor.placeColumns();
        dlmonitor.updateAll(true); // 仅布局变更，不重新加载数据
        return;
    }
    
    // 更新剩余列的索引
    remainingColumns.each(function(i) {
        var column = $(this);
        
        if (i >= kwList.length) {
            console.error("索引超出范围:", i, "关键字列表长度:", kwList.length);
            return;
        }
        
        var kw = kwList[i];
        console.log("更新列索引:", i, "关键字:", kw);
        
        // 更新标题和关键字
        column.find(".panel-heading h3").attr("id", "column-title-" + i).text(kw);
        column.find(".panel-body").attr("id", "posts-" + i);
        column.find(".close-btn").attr("id", "close-btn-" + i).data("keyword", kw);
        
        // 更新排序控制元素
        var sortType = dlmonitor.getSortPreference(kw);
        column.find(".sort-control span").attr("id", "sort-info-" + i);
        column.find("#sort-info-" + i).html(dlmonitor.getSortHtml(sortType));
        
        // 更新排序选项的data-index属性
        column.find(".sort-option").each(function() {
            $(this).attr("data-index", i);
        });
        
        // 移除临时标记
        column.removeAttr("data-column-index");
    });
};

// 排序偏好处理
dlmonitor.loadSortPreferences = function() {
    var sortPrefs = Cookies.get('sortPreferences');
    if (sortPrefs) {
        try {
            dlmonitor.sortPreferences = JSON.parse(sortPrefs);
        } catch (e) {
            console.error("Failed to parse sort preferences", e);
            dlmonitor.sortPreferences = {};
        }
    }
};

dlmonitor.saveSortPreferences = function() {
    Cookies.set('sortPreferences', JSON.stringify(dlmonitor.sortPreferences));
};

dlmonitor.getSortPreference = function(keyword) {
    return dlmonitor.sortPreferences[keyword] || 'time';
};

// 设置排序和刷新数据
dlmonitor.sortColumn = function(index, sortType) {
    // 确保index是数字类型
    index = parseInt(index, 10);
    if (isNaN(index)) {
        console.error("无效的列索引:", index);
        return;
    }
    
    var $columnTitle = $("#column-title-" + index);
    if ($columnTitle.length === 0) {
        console.error("找不到列标题元素:", index);
        return;
    }
    
    var kw = $columnTitle.text();
    console.log("设置列排序:", index, "关键字:", kw, "排序类型:", sortType);
    
    // 关闭所有下拉菜单
    $('.dropdown-content').addClass('hidden');
    
    // 更新排序偏好
    dlmonitor.sortPreferences[kw] = sortType;
    dlmonitor.saveSortPreferences();
    
    // 更新UI
    $("#sort-info-" + index).html(dlmonitor.getSortHtml(sortType));
    
    // 重新加载数据
    var parts = kw.split(":");
    if (parts.length === 2) {
        var src = parts[0];
        dlmonitor.fetch(src, kw, index, 0, sortType);
    }
};

// 获取数据
dlmonitor.fetch = function(src_name, keyword, index, start, sortType) {
    if (start == undefined) start = 0;
    if (sortType == undefined) sortType = dlmonitor.getSortPreference(keyword);
    
    console.log("Fetching data for column:", index, "keyword:", keyword, "sort:", sortType);
    
    var $postsElement = $("#posts-" + index);
    if ($postsElement.length === 0) {
        console.error("Cannot find element #posts-" + index);
        return;
    }
    
    $postsElement.html(
        "<div style='text-align:center;'>"+
        "<img src='https://cdnjs.cloudflare.com/ajax/libs/semantic-ui/0.16.1/images/loader-large.gif'/>"+
        "<p>Loading...</p>"+
        "</div>");
    dlmonitor.ajaxCount++;
    
    // 获取日期范围
    var datetoken = Cookies.get('datetoken') || '2-week';
    
    // 发送AJAX请求
    $.ajax({
       url: '/fetch',
       type: 'POST',
       timeout: 20000,
       data: {
          src: src_name,
          start: "" + start,
          keyword: keyword,
          datetoken: datetoken,
          sort: sortType
       },
       error: function(xhr, status, error) {
           dlmonitor.ajaxCount--;
           console.error("Error fetching data:", error, "Status:", status, "For column:", index);
           $postsElement.html(
               "<div class='error-message'>Failed to load data. " +
               "<button class='btn btn-default retry-btn' data-src='" + 
               src_name + "' data-keyword='" + keyword + "' data-index='" + index + "'>Retry</button></div>"
           );
       },
       success: function(data) {
          console.log("Successfully loaded data for column", index);
          dlmonitor.ajaxCount--;
          if (data && data.trim().length > 0) {
              $postsElement.html(data);
          } else {
              console.warn("Empty response for column", index);
              $postsElement.html("<div class='empty-message'>No results found.</div>");
          }
       },
       complete: function() {
          if (dlmonitor.ajaxCount > 0) {
              dlmonitor.ajaxCount--;
          }
       }
    });
};

// 日期相关函数
dlmonitor.convertDateInfo = function(token) {
    switch (token) {
        case 'today': return "Today";
        case '2-days': return "Last 2 days";
        case '1-week': return "Last week";
        case '1-month': return "Last month";
        default: return "Last week";
    }
};

dlmonitor.showDate = function() {
    var datetoken = Cookies.get('datetoken') || '2-week';
    $("#date-info").text(dlmonitor.convertDateInfo(datetoken));
};

dlmonitor.filterDate = function(token) {
    Cookies.set('datetoken', token);
    // 更新界面上的日期显示
    dlmonitor.showDate();
    // 重新加载所有数据
    dlmonitor.updateAll();
};

// 放置列
dlmonitor.placeColumns = function() {
    var kwList = dlmonitor.getKeywords();
    var currentNum = $(".post-columns .column").length;
    
    console.log("重新布局列，当前列数:", currentNum, "目标列数:", kwList.length);
    
    // 创建列或重新排列列
    if (kwList.length != currentNum) {
        console.log("需要重新创建列，当前:", currentNum, "目标:", kwList.length);
        
        // 保存现有列的内容
        var columnContents = {};
        $(".post-columns .column").each(function(i) {
            var panelBody = $(this).find(".panel-body");
            var panelId = panelBody.attr("id");
            if (panelId) {
                var index = parseInt(panelId.split("-")[1], 10);
                if (!isNaN(index) && index < kwList.length) {
                    columnContents[kwList[index]] = panelBody.html();
                    console.log("保存列内容:", index, kwList[index]);
                }
            }
        });
        
        // 创建新的列HTML
        var newHtml = "";
        for (var i = 0; i < kwList.length; ++i) {
            var template = $("#column-template").html();
            template = template.replace(/NUM/g, "" + i);
            newHtml += template;
        }
        $("#post-columns").html(newHtml);
        
        // 填充标题和设置属性
        for (var i = 0; i < kwList.length; ++i) {
            var kw = kwList[i];
            console.log("设置列:", i, "关键字:", kw);
            
            // 更新标题和关闭按钮
            $("#column-title-" + i).html(kw);
            $("#close-btn-" + i).data("keyword", kw);
            
            // 设置排序偏好
            var sortType = dlmonitor.getSortPreference(kw);
            $("#sort-info-" + i).html(dlmonitor.getSortHtml(sortType));
            
            // 确保排序选项的data-index属性正确
            $("#post-columns .column").eq(i).find('.sort-option').each(function() {
                $(this).attr('data-index', i);
                console.log("设置排序选项 data-index:", i, "for sort type:", $(this).data('sort'));
            });
            
            // 恢复列内容（如果有）
            if (columnContents[kw]) {
                $("#posts-" + i).html(columnContents[kw]);
                console.log("恢复列内容:", i, kw);
            }
        }
    } else {
        // 即使列数相同，也检查一下data-index是否正确
        for (var i = 0; i < kwList.length; ++i) {
            var $column = $("#post-columns .column").eq(i);
            var kw = kwList[i];
            
            // 确保标题和关键字正确
            $column.find(".panel-heading h3").attr("id", "column-title-" + i).text(kw);
            $column.find(".panel-body").attr("id", "posts-" + i);
            $column.find(".close-btn").attr("id", "close-btn-" + i).data("keyword", kw);
            
            // 检查排序选项
            $column.find('.sort-option').each(function() {
                var currentIndex = $(this).attr('data-index');
                if (currentIndex != i) {
                    console.log("修复排序选项 data-index，从", currentIndex, "到", i);
                    $(this).attr('data-index', i);
                }
            });
        }
    }
    
    // 双重检查所有列是否都具有正确的关键字
    $(".post-columns .column").each(function(i) {
        if (i < kwList.length) {
            var titleText = $(this).find(".panel-title").text();
            var kw = kwList[i];
            if (titleText !== kw) {
                console.warn("列标题不匹配，修复:", i, "当前:", titleText, "应为:", kw);
                $(this).find(".panel-title").text(kw);
                $(this).find(".close-btn").data("keyword", kw);
            }
        }
    });
};

// 更新所有列
dlmonitor.updateAll = function(reload) {
    console.log("开始执行 updateAll 函数，reload=", reload);

    // 让链接回来时不会被点击，而是显示链接
    $("body,html").animate({scrollTop: 0}, 200);
    $(".loading-msg").empty().append("<p>Loading data...</p>");
    $(".loading").show();

    var keywords = dlmonitor.getKeywords();
    $("body").toggleClass("loading-state", true);
    var kw_list = [];

    // 确保列布局正确
    dlmonitor.placeColumns();

    // 对已有的列做排序控制，确认正确的索引
    console.log("检查排序控制索引...");
    $(".sort-info").each(function(idx, elem) {
        var colIdx = $(elem).closest('.panel-body').attr('id').split('-')[2];
        console.log("列索引:", colIdx, "排序控制:", $(elem).attr('id'));
        // 更新排序选项的 data-index 属性
        $(elem).find('.sort-option').attr('data-index', colIdx);
    });

    console.log("开始准备加载数据...");
    
    // 如果只是布局变更，无需重新加载数据
    if (reload === true) {
        console.log("仅布局变更，不加载数据");
        $("body").toggleClass("loading-state", false);
        $(".loading").hide();
        return;
    }
    
    // 清空所有列内容，确保重新加载
    for (var i = 0; i < keywords.length; i++) {
        $("#posts-" + i).html(
            "<div style='text-align:center;'>"+
            "<img src='https://cdnjs.cloudflare.com/ajax/libs/semantic-ui/0.16.1/images/loader-large.gif'/>"+
            "<p>Loading...</p>"+
            "</div>"
        );
    }
    
    // 加载所有关键词数据
    loadKeyword(0);

    function loadKeyword(idx) {
        if (idx >= keywords.length) {
            console.log("所有数据加载完成");
            $("body").toggleClass("loading-state", false);
            $(".loading").hide();
            return;
        }

        var kw = keywords[idx];
        var sort_type = dlmonitor.getSortPreference(kw);
        console.log("开始加载关键词数据:", idx, kw, "排序:", sort_type);
        
        var parts = kw.split(":");
        if (parts.length === 2) {
            var src = parts[0];
            
            // 使用fetch函数获取数据
            dlmonitor.fetch(src, kw, idx, 0, sort_type);
            
            // 继续加载下一个关键词
            setTimeout(function() {
                loadKeyword(idx + 1);
            }, 150); // 错开请求时间
        } else {
            // 无效的关键词格式，跳过并继续
            console.error("无效的关键词格式:", kw);
            loadKeyword(idx + 1);
        }
    }
};

// 预览切换
dlmonitor.switchPreview = function(flag) {
    if (flag) {
        $(".preview").show();
        $(".post-columns").hide();
    } else {
        $(".preview").hide();
        $(".post-columns").show();
    }
};

// 初始化
dlmonitor.init = function() {
    console.log("开始初始化应用程序...");
    
    // 加载排序偏好
    dlmonitor.loadSortPreferences();
    console.log("排序偏好已加载");
    
    // 设置下拉菜单 - 移至setTimeout中确保DOM完全加载
    setTimeout(function() {
        dlmonitor.setupDropdowns();
        console.log("下拉菜单已设置");
    }, 100);
    
    // 初始化列并加载数据
    dlmonitor.updateAll();
    
    // 绑定添加关键字的事件
    $("#new-keyword").keypress(function(e) {
        if(e.which == 13) {
            dlmonitor.addKeyword();
            return false;
        }
    });
    $("#new-keyword-btn").click(function(){
        dlmonitor.addKeyword();
    });
    console.log("关键字输入事件已绑定");
    
    // 绑定预览功能
    $('#new-keyword').on('keyup', function() {
        clearTimeout(dlmonitor.previewTimeout);
        dlmonitor.previewTimeout = setTimeout(function() {
            var text = $("#new-keyword").val();
            if ($("#new-keyword").is(":focus") && text.length >= 3) {
                $("#preview-kw").html(dlmonitor.currentPlatform + ":" + text);
                $("#posts-preview").height(($(window).height() - 160) + "px")
                dlmonitor.switchPreview(true);
                dlmonitor.fetch(dlmonitor.currentPlatform, dlmonitor.currentPlatform + ":" + text, 'preview');
            } else {
                dlmonitor.switchPreview(false);
            }
        }, 200);
        if ($("#new-keyword").val().length < 3) {
            dlmonitor.switchPreview(false);
        }
    });
    console.log("预览功能已启用");
    
    // 使用事件委托绑定各种交互事件
    console.log("设置事件委托...");
    
    // 1. 排序选项点击绑定已经移到setupDropdowns中处理
    
    // 2. 绑定删除按钮
    $(document).off('click', '.close-btn');
    $(document).on('click', '.close-btn', function(e) {
        // 如果是预览关闭按钮，特殊处理
        if($(this).attr('id') === 'close-btn-preview') {
            dlmonitor.switchPreview(false);
            $("#new-keyword").val('');
            console.log("关闭预览面板");
        } else {
            // 否则执行普通删除
            dlmonitor.removeKeyword(this);
        }
    });
    
    // 确保预览关闭按钮始终有效
    $("#close-btn-preview").off('click');
    $("#close-btn-preview").on('click', function() {
        dlmonitor.switchPreview(false);
        $("#new-keyword").val('');
        console.log("通过直接绑定关闭预览面板");
    });
    
    // 3. 绑定重试按钮
    $(document).off('click', '.retry-btn');
    $(document).on('click', '.retry-btn', function() {
        var src = $(this).data('src');
        var keyword = $(this).data('keyword');
        var idx = $(this).data('index');
        var sortType = dlmonitor.getSortPreference(keyword) || 'time';
        dlmonitor.fetch(src, keyword, idx, 0, sortType);
    });
    
    // 4. 绑定强制刷新按钮
    $(document).off('click', '.refresh-btn');
    $(document).on('click', '.refresh-btn', function() {
        var idx = $(this).data('index');
        dlmonitor.forceRefreshColumn(idx);
    });
    
    // 在页面加载一段时间后，再次确保下拉菜单都能正常工作
    setTimeout(function() {
        console.log("重新设置下拉菜单事件...");
        dlmonitor.setupDropdowns();
    }, 1000);
    
    console.log("初始化完成，所有事件绑定已设置");
};

// 初始化
$(function(){
    dlmonitor.init();
});

// 强制刷新列
dlmonitor.forceRefreshColumn = function(index) {
    var kwList = dlmonitor.getKeywords();
    if (index >= kwList.length) {
        console.error("Invalid column index:", index);
        return;
    }
    
    var keyword = kwList[index];
    var parts = keyword.split(":");
    if (parts.length === 2) {
        var src = parts[0];
        console.log("Force refreshing column:", index, "keyword:", keyword);
        
        // 显示加载中
        $("#posts-" + index).html(
            "<div style='text-align:center;'>"+
            "<img src='https://cdnjs.cloudflare.com/ajax/libs/semantic-ui/0.16.1/images/loader-large.gif'/>"+
            "<p>Refreshing...</p>"+
            "</div>"
        );
        
        var datetoken = Cookies.get('datetoken') || '2-week';
        var sortType = dlmonitor.getSortPreference(keyword);
        
        // 创建表单并提交，强制刷新
        var $form = $('<form action="/fetch" method="POST" target="refresh_frame_' + index + '"></form>');
        $form.append('<input type="hidden" name="src" value="' + src + '">');
        $form.append('<input type="hidden" name="start" value="0">');
        $form.append('<input type="hidden" name="keyword" value="' + keyword + '">');
        $form.append('<input type="hidden" name="datetoken" value="' + datetoken + '">');
        $form.append('<input type="hidden" name="sort" value="' + sortType + '">');
        
        // 创建隐藏iframe接收结果
        var $iframe = $('<iframe name="refresh_frame_' + index + '" style="display:none;"></iframe>');
        $('body').append($iframe);
        
        // 设置iframe加载完成后的回调
        $iframe.on('load', function() {
            try {
                var content = $iframe.contents().find('body').html();
                if (content && content.length > 0) {
                    $("#posts-" + index).html(content);
                    console.log("Force refresh successful for column", index);
                } else {
                    $("#posts-" + index).html(
                        "<div class='error-message'>Refresh failed. " +
                        "<button class='btn btn-default retry-btn' data-src='" + 
                        src + "' data-keyword='" + keyword + "' data-index='" + index + "'>Try Again</button></div>"
                    );
                }
            } catch (e) {
                console.error("Error processing iframe content:", e);
                $("#posts-" + index).html(
                    "<div class='error-message'>Refresh error. " +
                    "<button class='btn btn-default' onclick='window.location.reload()'>Reload Page</button></div>"
                );
            }
            
            // 清理iframe
            setTimeout(function() { $iframe.remove(); }, 1000);
        });
        
        // 提交表单并清理
        $('body').append($form);
        $form.submit();
        setTimeout(function() { $form.remove(); }, 1000);
    }
};
