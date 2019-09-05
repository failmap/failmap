'use strict';

Object.defineProperty(exports, '__esModule', { value: true });

function _interopDefault (ex) { return (ex && (typeof ex === 'object') && 'default' in ex) ? ex['default'] : ex; }

var leaflet = require('leaflet');
var Vue = _interopDefault(require('vue'));

var debounce = function (fn, time) {
  var timeout;

  return function () {
    var args = [], len = arguments.length;
    while ( len-- ) args[ len ] = arguments[ len ];

    var context = this;
    if (timeout) {
      clearTimeout(timeout);
    }
    timeout = setTimeout(function () {
      fn.apply(context, args);
      timeout = null;
    }, time);
  };
};

var capitalizeFirstLetter = function (string) {
  if (!string || typeof string.charAt !== 'function') { return string; }
  return string.charAt(0).toUpperCase() + string.slice(1);
};

var propsBinder = function (vueElement, leafletElement, props, options) {
  var loop = function ( key ) {
    var setMethodName = 'set' + capitalizeFirstLetter(key);
    var deepValue = (props[key].type === Object) ||
      (props[key].type === Array) ||
      (Array.isArray(props[key].type));
    if (props[key].custom && vueElement[setMethodName]) {
      vueElement.$watch(key, function (newVal, oldVal) {
        vueElement[setMethodName](newVal, oldVal);
      }, {
        deep: deepValue
      });
    } else if (setMethodName === 'setOptions') {
      vueElement.$watch(key, function (newVal, oldVal) {
        leaflet.setOptions(leafletElement, newVal);
      }, {
        deep: deepValue
      });
    } else if (leafletElement[setMethodName]) {
      vueElement.$watch(key, function (newVal, oldVal) {
        leafletElement[setMethodName](newVal);
      }, {
        deep: deepValue
      });
    }
  };

  for (var key in props) loop( key );
};

var collectionCleaner = function (options) {
  var result = {};
  for (var key in options) {
    var value = options[key];
    if (value !== null && value !== undefined) {
      result[key] = value;
    }
  }
  return result;
};

var optionsMerger = function (props, instance) {
  var options = instance.options && instance.options.constructor === Object ? instance.options : {};
  props = props && props.constructor === Object ? props : {};
  var result = collectionCleaner(options);
  props = collectionCleaner(props);
  var defaultProps = instance.$options.props;
  for (var key in props) {
    var def = defaultProps[key] ? defaultProps[key].default : Symbol('unique');
    if (result[key] && def !== props[key]) {
      console.warn((key + " props is overriding the value passed in the options props"));
      result[key] = props[key];
    } else if (!result[key]) {
      result[key] = props[key];
    }
  }  return result;
};

var findRealParent = function (firstVueParent) {
  var found = false;
  while (firstVueParent && !found) {
    if (firstVueParent.mapObject === undefined) {
      firstVueParent = firstVueParent.$parent;
    } else {
      found = true;
    }
  }
  return firstVueParent;
};

var Layer = {
  props: {
    pane: {
      type: String,
      default: 'overlayPane'
    },
    attribution: {
      type: String,
      default: null
    },
    name: {
      type: String,
      custom: true,
      default: undefined
    },
    layerType: {
      type: String,
      custom: true,
      default: undefined
    },
    visible: {
      type: Boolean,
      custom: true,
      default: true
    }
  },
  mounted: function mounted () {
    this.layerOptions = {
      attribution: this.attribution,
      pane: this.pane
    };
  },
  beforeDestroy: function beforeDestroy () {
    this.unbindPopup();
    this.unbindTooltip();
    this.parentContainer.removeLayer(this);
  },
  methods: {
    setAttribution: function setAttribution (val, old) {
      var attributionControl = this.$parent.mapObject.attributionControl;
      attributionControl.removeAttribution(old).addAttribution(val);
    },
    setName: function setName () {
      this.parentContainer.removeLayer(this);
      if (this.visible) {
        this.parentContainer.addLayer(this);
      }
    },
    setLayerType: function setLayerType () {
      this.parentContainer.removeLayer(this);
      if (this.visible) {
        this.parentContainer.addLayer(this);
      }
    },
    setVisible: function setVisible (newVal) {
      if (this.mapObject) {
        if (newVal) {
          this.parentContainer.addLayer(this);
        } else {
          this.parentContainer.removeLayer(this);
        }
      }
    },
    unbindTooltip: function unbindTooltip () {
      var tooltip = this.mapObject ? this.mapObject.getTooltip() : null;
      if (tooltip) {
        tooltip.unbindTooltip();
      }
    },
    unbindPopup: function unbindPopup () {
      var popup = this.mapObject ? this.mapObject.getPopup() : null;
      if (popup) {
        popup.unbindPopup();
      }
    }
  }
};

var InteractiveLayer = {
  props: {
    interactive: {
      type: Boolean,
      default: true
    },
    bubblingMouseEvents: {
      type: Boolean,
      default: true
    }
  },
  mounted: function mounted () {
    this.interactiveLayerOptions = {
      interactive: this.interactive,
      bubblingMouseEvents: this.bubblingMouseEvents
    };
  }
};

var Path = {
  mixins: [Layer, InteractiveLayer],
  props: {
    lStyle: {
      type: Object,
      custom: true,
      default: null
    },
    stroke: {
      type: Boolean,
      custom: true,
      default: true
    },
    color: {
      type: String,
      custom: true,
      default: '#3388ff'
    },
    weight: {
      type: Number,
      custom: true,
      default: 3
    },
    opacity: {
      type: Number,
      custom: true,
      default: 1.0
    },
    lineCap: {
      type: String,
      custom: true,
      default: 'round'
    },
    lineJoin: {
      type: String,
      custom: true,
      default: 'round'
    },
    dashArray: {
      type: String,
      custom: true,
      default: null
    },
    dashOffset: {
      type: String,
      custom: true,
      default: null
    },
    fill: {
      type: Boolean,
      custom: true,
      default: false
    },
    fillColor: {
      type: String,
      custom: true,
      default: '#3388ff'
    },
    fillOpacity: {
      type: Number,
      custom: true,
      default: 0.2
    },
    fillRule: {
      type: String,
      custom: true,
      default: 'evenodd'
    },
    className: {
      type: String,
      custom: true,
      default: null
    }
  },
  mounted: function mounted () {
    this.pathOptions = Object.assign({}, this.layerOptions,
      this.interactiveLayerOptions,
      {stroke: this.stroke,
      color: this.color,
      weight: this.weight,
      opacity: this.opacity,
      lineCap: this.lineCap,
      lineJoin: this.lineJoin,
      dashArray: this.dashArray,
      dashOffset: this.dashOffset,
      fill: this.fill,
      fillColor: this.fillColor,
      fillOpacity: this.fillOpacity,
      fillRule: this.fillRule,
      className: this.className});

    if (this.lStyle) {
      console.warn('lStyle is deprecated and is going to be removed in the next major version');
      for (var style in this.lStyle) {
        this.pathOptions[style] = this.lStyle[style];
      }
    }
  },
  beforeDestroy: function beforeDestroy () {
    if (this.parentContainer) {
      this.parentContainer.removeLayer(this);
    } else {
      console.error('Missing parent container');
    }
  },
  methods: {
    setLStyle: function setLStyle (newVal) {
      this.mapObject.setStyle(newVal);
    },
    setStroke: function setStroke (newVal) {
      this.mapObject.setStyle({ stroke: newVal });
    },
    setColor: function setColor (newVal) {
      this.mapObject.setStyle({ color: newVal });
    },
    setWeight: function setWeight (newVal) {
      this.mapObject.setStyle({ weight: newVal });
    },
    setOpacity: function setOpacity (newVal) {
      this.mapObject.setStyle({ opacity: newVal });
    },
    setLineCap: function setLineCap (newVal) {
      this.mapObject.setStyle({ lineCap: newVal });
    },
    setLineJoin: function setLineJoin (newVal) {
      this.mapObject.setStyle({ lineJoin: newVal });
    },
    setDashArray: function setDashArray (newVal) {
      this.mapObject.setStyle({ dashArray: newVal });
    },
    setDashOffset: function setDashOffset (newVal) {
      this.mapObject.setStyle({ dashOffset: newVal });
    },
    setFill: function setFill (newVal) {
      this.mapObject.setStyle({ fill: newVal });
    },
    setFillColor: function setFillColor (newVal) {
      this.mapObject.setStyle({ fillColor: newVal });
    },
    setFillOpacity: function setFillOpacity (newVal) {
      this.mapObject.setStyle({ fillOpacity: newVal });
    },
    setFillRule: function setFillRule (newVal) {
      this.mapObject.setStyle({ fillRule: newVal });
    },
    setClassName: function setClassName (newVal) {
      this.mapObject.setStyle({ className: newVal });
    }
  }
};

var CircleMixin = {
  mixins: [Path],
  props: {
    fill: {
      type: Boolean,
      custom: true,
      default: true
    },
    radius: {
      type: Number,
      default: null
    }
  },
  mounted: function mounted () {
    this.circleOptions = Object.assign({}, this.pathOptions,
      {radius: this.radius});
  }
};

var ControlMixin = {
  props: {
    position: {
      type: String,
      default: 'topright'
    }
  },
  mounted: function mounted () {
    this.controlOptions = {
      position: this.position
    };
  },
  beforeDestroy: function beforeDestroy () {
    if (this.mapObject) {
      this.mapObject.remove();
    }
  }
};

var GridLayerMixin = {
  mixins: [Layer],
  props: {
    pane: {
      type: String,
      default: 'tilePane'
    },
    opacity: {
      type: Number,
      custom: false,
      default: 1.0
    },
    zIndex: {
      type: Number,
      default: 1
    },
    tileSize: {
      type: Number,
      default: 256
    },
    noWrap: {
      type: Boolean,
      default: false
    }
  },
  mounted: function mounted () {
    this.gridLayerOptions = Object.assign({}, this.layerOptions,
      {pane: this.pane,
      opacity: this.opacity,
      zIndex: this.zIndex,
      tileSize: this.tileSize,
      noWrap: this.noWrap});
  }
};

var ImageOverlayMixin = {
  mixins: [Layer, InteractiveLayer],
  props: {
    url: {
      type: String,
      custom: true
    },
    bounds: {
      custom: true
    },
    opacity: {
      type: Number,
      custom: true,
      default: 1.0
    },
    alt: {
      type: String,
      default: ''
    },
    interactive: {
      type: Boolean,
      default: false
    },
    crossOrigin: {
      type: Boolean,
      default: false
    },
    errorOverlayUrl: {
      type: String,
      custom: true,
      default: ''
    },
    zIndex: {
      type: Number,
      custom: true,
      default: 1
    },
    className: {
      type: String,
      default: ''
    }
  },
  mounted: function mounted () {
    this.imageOverlayOptions = Object.assign({}, this.layerOptions,
      this.interactiveLayerOptions,
      {opacity: this.opacity,
      alt: this.alt,
      interactive: this.interactive,
      crossOrigin: this.crossOrigin,
      errorOverlayUrl: this.errorOverlayUrl,
      zIndex: this.zIndex,
      className: this.className});
  },
  methods: {
    setOpacity: function setOpacity (opacity) {
      return this.mapObject.setOpacity(opacity);
    },
    setUrl: function setUrl (url) {
      return this.mapObject.setUrl(url);
    },
    setBounds: function setBounds (bounds) {
      return this.mapObject.setBounds(bounds);
    },
    getBounds: function getBounds () {
      return this.mapObject.getBounds();
    },
    getElement: function getElement () {
      return this.mapObject.getElement();
    },
    bringToFront: function bringToFront () {
      return this.mapObject.bringToFront();
    },
    bringToBack: function bringToBack () {
      return this.mapObject.bringToBack();
    }
  },
  render: function render () {
    return null;
  }
};

var LayerGroupMixin = {
  mixins: [Layer],
  mounted: function mounted () {
    this.layerGroupOptions = this.layerOptions;
  },
  methods: {
    addLayer: function addLayer (layer, alreadyAdded) {
      if (!alreadyAdded) {
        this.mapObject.addLayer(layer.mapObject);
      }
      this.parentContainer.addLayer(layer, true);
    },
    removeLayer: function removeLayer (layer, alreadyRemoved) {
      if (!alreadyRemoved) {
        this.mapObject.removeLayer(layer.mapObject);
      }
      this.parentContainer.removeLayer(layer, true);
    }
  }
};

var Options = {
  props: {
    options: {
      type: Object,
      default: function () { return ({}); }
    }
  }
};

var PolylineMixin = {
  mixins: [Path],
  props: {
    smoothFactor: {
      type: Number,
      custom: true,
      default: 1.0
    },
    noClip: {
      type: Boolean,
      custom: true,
      default: false
    }
  },
  data: function data () {
    return {
      ready: false
    };
  },
  mounted: function mounted () {
    this.polyLineOptions = Object.assign({}, this.pathOptions,
      {smoothFactor: this.smoothFactor,
      noClip: this.noClip});
  },
  methods: {
    setSmoothFactor: function setSmoothFactor (newVal) {
      this.mapObject.setStyle({ smoothFactor: newVal });
    },
    setNoClip: function setNoClip (newVal) {
      this.mapObject.setStyle({ noClip: newVal });
    },
    addLatLng: function addLatLng (value) {
      this.mapObject.addLatLng(value);
    }
  }
};

var Polygon = {
  mixins: [PolylineMixin],
  props: {
    fill: {
      type: Boolean,
      custom: true,
      default: true
    }
  },
  mounted: function mounted () {
    this.polygonOptions = this.polyLineOptions;
  },
  methods: {
    getGeoJSONData: function getGeoJSONData () {
      return this.mapObject.toGeoJSON();
    }
  }
};

var Popper = {
  props: {
    content: {
      type: String,
      default: null,
      custom: true
    }
  },
  mounted: function mounted () {
    this.popperOptions = {};
  },
  methods: {
    setContent: function setContent (newVal) {
      if (this.mapObject && newVal !== null && newVal !== undefined) {
        this.mapObject.setContent(newVal);
      }
    }
  },
  render: function render (h) {
    if (this.$slots.default) {
      return h('div', this.$slots.default);
    }
    return null;
  }
};

var TileLayerMixin = {
  mixins: [GridLayerMixin],
  props: {
    tms: {
      type: Boolean,
      default: false
    },
    detectRetina: {
      type: Boolean,
      default: false
    }
  },
  mounted: function mounted () {
    this.tileLayerOptions = Object.assign({}, this.gridLayerOptions,
      {tms: this.tms,
      detectRetina: this.detectRetina});
  },
  render: function render () {
    return null;
  }
};

var TileLayerWMS = {
  mixins: [TileLayerMixin],
  props: {
    layers: {
      type: String,
      default: ''
    },
    styles: {
      type: String,
      default: ''
    },
    format: {
      type: String,
      default: 'image/jpeg'
    },
    transparent: {
      type: Boolean,
      custom: false
    },
    version: {
      type: String,
      default: '1.1.1'
    },
    crs: {
      default: null
    },
    upperCase: {
      type: Boolean,
      default: false
    }
  },
  mounted: function mounted () {
    this.tileLayerWMSOptions = Object.assign({}, this.tileLayerOptions,
      {layers: this.layers,
      styles: this.styles,
      format: this.format,
      transparent: this.transparent,
      version: this.version,
      crs: this.crs,
      upperCase: this.upperCase});
  }
};

//

var script = {
  name: 'LCircle',
  mixins: [CircleMixin],
  props: {
    latLng: {
      type: [Object, Array],
      default: function () { return [0, 0]; }
    }
  },
  data: function data () {
    return {
      ready: false
    };
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.circleOptions, this);
    this.mapObject = leaflet.circle(this.latLng, options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.ready = true;
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  methods: {}
};

function normalizeComponent(template, style, script, scopeId, isFunctionalTemplate, moduleIdentifier
/* server only */
, shadowMode, createInjector, createInjectorSSR, createInjectorShadow) {
  if (typeof shadowMode !== 'boolean') {
    createInjectorSSR = createInjector;
    createInjector = shadowMode;
    shadowMode = false;
  } // Vue.extend constructor export interop.


  var options = typeof script === 'function' ? script.options : script; // render functions

  if (template && template.render) {
    options.render = template.render;
    options.staticRenderFns = template.staticRenderFns;
    options._compiled = true; // functional template

    if (isFunctionalTemplate) {
      options.functional = true;
    }
  } // scopedId


  if (scopeId) {
    options._scopeId = scopeId;
  }

  var hook;

  if (moduleIdentifier) {
    // server build
    hook = function hook(context) {
      // 2.3 injection
      context = context || // cached call
      this.$vnode && this.$vnode.ssrContext || // stateful
      this.parent && this.parent.$vnode && this.parent.$vnode.ssrContext; // functional
      // 2.2 with runInNewContext: true

      if (!context && typeof __VUE_SSR_CONTEXT__ !== 'undefined') {
        context = __VUE_SSR_CONTEXT__;
      } // inject component styles


      if (style) {
        style.call(this, createInjectorSSR(context));
      } // register component module identifier for async chunk inference


      if (context && context._registeredComponents) {
        context._registeredComponents.add(moduleIdentifier);
      }
    }; // used by ssr in case component is cached and beforeCreate
    // never gets called


    options._ssrRegister = hook;
  } else if (style) {
    hook = shadowMode ? function () {
      style.call(this, createInjectorShadow(this.$root.$options.shadowRoot));
    } : function (context) {
      style.call(this, createInjector(context));
    };
  }

  if (hook) {
    if (options.functional) {
      // register for functional component in vue file
      var originalRender = options.render;

      options.render = function renderWithStyleInjection(h, context) {
        hook.call(context);
        return originalRender(h, context);
      };
    } else {
      // inject component registration as beforeCreate hook
      var existing = options.beforeCreate;
      options.beforeCreate = existing ? [].concat(existing, hook) : [hook];
    }
  }

  return script;
}

var normalizeComponent_1 = normalizeComponent;

/* script */
var __vue_script__ = script;

/* template */
var __vue_render__ = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',{staticStyle:{"display":"none"}},[(_vm.ready)?_vm._t("default"):_vm._e()],2)};
var __vue_staticRenderFns__ = [];

  /* style */
  var __vue_inject_styles__ = undefined;
  /* scoped */
  var __vue_scope_id__ = undefined;
  /* module identifier */
  var __vue_module_identifier__ = undefined;
  /* functional template */
  var __vue_is_functional_template__ = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LCircle = normalizeComponent_1(
    { render: __vue_render__, staticRenderFns: __vue_staticRenderFns__ },
    __vue_inject_styles__,
    __vue_script__,
    __vue_scope_id__,
    __vue_is_functional_template__,
    __vue_module_identifier__,
    undefined,
    undefined
  );

//

var script$1 = {
  name: 'LCircleMarker',
  mixins: [CircleMixin],
  props: {
    latLng: {
      type: [Object, Array],
      default: function () { return [0, 0]; }
    },
    pane: {
      type: String,
      default: 'markerPane'
    }
  },
  data: function data () {
    return {
      ready: false
    };
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.circleOptions, this);
    this.mapObject = leaflet.circleMarker(this.latLng, options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.ready = true;
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  }
};

/* script */
var __vue_script__$1 = script$1;

/* template */
var __vue_render__$1 = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',{staticStyle:{"display":"none"}},[(_vm.ready)?_vm._t("default"):_vm._e()],2)};
var __vue_staticRenderFns__$1 = [];

  /* style */
  var __vue_inject_styles__$1 = undefined;
  /* scoped */
  var __vue_scope_id__$1 = undefined;
  /* module identifier */
  var __vue_module_identifier__$1 = undefined;
  /* functional template */
  var __vue_is_functional_template__$1 = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LCircleMarker = normalizeComponent_1(
    { render: __vue_render__$1, staticRenderFns: __vue_staticRenderFns__$1 },
    __vue_inject_styles__$1,
    __vue_script__$1,
    __vue_scope_id__$1,
    __vue_is_functional_template__$1,
    __vue_module_identifier__$1,
    undefined,
    undefined
  );

//

var script$2 = {
  name: 'LControl',
  mixins: [ControlMixin, Options],
  props: {
    disableClickPropagation: {
      type: Boolean,
      custom: true,
      default: true
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var LControl = leaflet.Control.extend({
      element: undefined,
      onAdd: function onAdd () {
        return this.element;
      },
      setElement: function setElement (el) {
        this.element = el;
      }
    });
    var options = optionsMerger(this.controlOptions, this);
    this.mapObject = new LControl(options);
    propsBinder(this, this.mapObject, this.$options.props);
    this.parentContainer = findRealParent(this.$parent);
    this.mapObject.setElement(this.$el);
    if (this.disableClickPropagation) {
      leaflet.DomEvent.disableClickPropagation(this.$el);
    }
    this.mapObject.addTo(this.parentContainer.mapObject);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  }
};

/* script */
var __vue_script__$2 = script$2;

/* template */
var __vue_render__$2 = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',[_vm._t("default")],2)};
var __vue_staticRenderFns__$2 = [];

  /* style */
  var __vue_inject_styles__$2 = undefined;
  /* scoped */
  var __vue_scope_id__$2 = undefined;
  /* module identifier */
  var __vue_module_identifier__$2 = undefined;
  /* functional template */
  var __vue_is_functional_template__$2 = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LControl = normalizeComponent_1(
    { render: __vue_render__$2, staticRenderFns: __vue_staticRenderFns__$2 },
    __vue_inject_styles__$2,
    __vue_script__$2,
    __vue_scope_id__$2,
    __vue_is_functional_template__$2,
    __vue_module_identifier__$2,
    undefined,
    undefined
  );

var script$3 = {
  name: 'LControlAttribution',
  mixins: [ControlMixin, Options],
  props: {
    prefix: {
      type: [String, Boolean],
      default: null
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(Object.assign({}, this.controlOptions,
      {prefix: this.prefix}), this);
    this.mapObject = leaflet.control.attribution(options);
    propsBinder(this, this.mapObject, this.$options.props);
    this.mapObject.addTo(this.$parent.mapObject);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  render: function render () {
    return null;
  }
};

/* script */
var __vue_script__$3 = script$3;

/* template */

  /* style */
  var __vue_inject_styles__$3 = undefined;
  /* scoped */
  var __vue_scope_id__$3 = undefined;
  /* module identifier */
  var __vue_module_identifier__$3 = undefined;
  /* functional template */
  var __vue_is_functional_template__$3 = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LControlAttribution = normalizeComponent_1(
    {},
    __vue_inject_styles__$3,
    __vue_script__$3,
    __vue_scope_id__$3,
    __vue_is_functional_template__$3,
    __vue_module_identifier__$3,
    undefined,
    undefined
  );

var script$4 = {
  name: 'LControlLayers',
  mixins: [ControlMixin, Options],
  props: {
    collapsed: {
      type: Boolean,
      default: true
    },
    autoZIndex: {
      type: Boolean,
      default: true
    },
    hideSingleBase: {
      type: Boolean,
      default: false
    },
    sortLayers: {
      type: Boolean,
      default: false
    },
    sortFunction: {
      type: Function,
      default: undefined
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(Object.assign({}, this.controlOptions,
      {collapsed: this.collapsed,
      autoZIndex: this.autoZIndex,
      hideSingleBase: this.hideSingleBase,
      sortLayers: this.sortLayers,
      sortFunction: this.sortFunction}), this);
    this.mapObject = leaflet.control.layers(null, null, options);
    propsBinder(this, this.mapObject, this.$options.props);
    this.$parent.registerLayerControl(this);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  methods: {
    addLayer: function addLayer (layer) {
      if (layer.layerType === 'base') {
        this.mapObject.addBaseLayer(layer.mapObject, layer.name);
      } else if (layer.layerType === 'overlay') {
        this.mapObject.addOverlay(layer.mapObject, layer.name);
      }
    },
    removeLayer: function removeLayer (layer) {
      this.mapObject.removeLayer(layer.mapObject);
    }
  },
  render: function render () {
    return null;
  }
};

/* script */
var __vue_script__$4 = script$4;

/* template */

  /* style */
  var __vue_inject_styles__$4 = undefined;
  /* scoped */
  var __vue_scope_id__$4 = undefined;
  /* module identifier */
  var __vue_module_identifier__$4 = undefined;
  /* functional template */
  var __vue_is_functional_template__$4 = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LControlLayers = normalizeComponent_1(
    {},
    __vue_inject_styles__$4,
    __vue_script__$4,
    __vue_scope_id__$4,
    __vue_is_functional_template__$4,
    __vue_module_identifier__$4,
    undefined,
    undefined
  );

var script$5 = {
  name: 'LControlScale',
  mixins: [ControlMixin, Options],
  props: {
    maxWidth: {
      type: Number,
      default: 100
    },
    metric: {
      type: Boolean,
      default: true
    },
    imperial: {
      type: Boolean,
      default: true
    },
    updateWhenIdle: {
      type: Boolean,
      default: false
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(Object.assign({}, this.controlOptions,
      {maxWidth: this.maxWidth,
      metric: this.metric,
      imperial: this.imperial,
      updateWhenIdle: this.updateWhenIdle}), this);
    this.mapObject = leaflet.control.scale(options);
    propsBinder(this, this.mapObject, this.$options.props);
    this.mapObject.addTo(this.$parent.mapObject);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  render: function render () {
    return null;
  }
};

/* script */
var __vue_script__$5 = script$5;

/* template */

  /* style */
  var __vue_inject_styles__$5 = undefined;
  /* scoped */
  var __vue_scope_id__$5 = undefined;
  /* module identifier */
  var __vue_module_identifier__$5 = undefined;
  /* functional template */
  var __vue_is_functional_template__$5 = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LControlScale = normalizeComponent_1(
    {},
    __vue_inject_styles__$5,
    __vue_script__$5,
    __vue_scope_id__$5,
    __vue_is_functional_template__$5,
    __vue_module_identifier__$5,
    undefined,
    undefined
  );

var script$6 = {
  name: 'LControlZoom',
  mixins: [ControlMixin, Options],
  props: {
    zoomInText: {
      type: String,
      default: '+'
    },
    zoomInTitle: {
      type: String,
      default: 'Zoom in'
    },
    zoomOutText: {
      type: String,
      default: '-'
    },
    zoomOutTitle: {
      type: String,
      default: 'Zoom out'
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(Object.assign({}, this.controlOptions,
      {zoomInText: this.zoomInText,
      zoomInTitle: this.zoomInTitle,
      zoomOutText: this.zoomOutText,
      zoomOutTitle: this.zoomOutTitle}), this);
    this.mapObject = leaflet.control.zoom(options);
    propsBinder(this, this.mapObject, this.$options.props);
    this.mapObject.addTo(this.$parent.mapObject);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  render: function render () {
    return null;
  }
};

/* script */
var __vue_script__$6 = script$6;

/* template */

  /* style */
  var __vue_inject_styles__$6 = undefined;
  /* scoped */
  var __vue_scope_id__$6 = undefined;
  /* module identifier */
  var __vue_module_identifier__$6 = undefined;
  /* functional template */
  var __vue_is_functional_template__$6 = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LControlZoom = normalizeComponent_1(
    {},
    __vue_inject_styles__$6,
    __vue_script__$6,
    __vue_scope_id__$6,
    __vue_is_functional_template__$6,
    __vue_module_identifier__$6,
    undefined,
    undefined
  );

//

var script$7 = {
  name: 'LFeatureGroup',
  mixins: [LayerGroupMixin],
  data: function data () {
    return {
      ready: false
    };
  },
  mounted: function mounted () {
    var this$1 = this;

    this.mapObject = leaflet.featureGroup();
    propsBinder(this, this.mapObject, this.$options.props);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    this.ready = true;
    this.parentContainer = findRealParent(this.$parent, true);
    if (this.visible) {
      this.parentContainer.addLayer(this);
    }
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  }
};

/* script */
var __vue_script__$7 = script$7;

/* template */
var __vue_render__$3 = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',{staticStyle:{"display":"none"}},[(_vm.ready)?_vm._t("default"):_vm._e()],2)};
var __vue_staticRenderFns__$3 = [];

  /* style */
  var __vue_inject_styles__$7 = undefined;
  /* scoped */
  var __vue_scope_id__$7 = undefined;
  /* module identifier */
  var __vue_module_identifier__$7 = undefined;
  /* functional template */
  var __vue_is_functional_template__$7 = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LFeatureGroup = normalizeComponent_1(
    { render: __vue_render__$3, staticRenderFns: __vue_staticRenderFns__$3 },
    __vue_inject_styles__$7,
    __vue_script__$7,
    __vue_scope_id__$7,
    __vue_is_functional_template__$7,
    __vue_module_identifier__$7,
    undefined,
    undefined
  );

var script$8 = {
  name: 'LGeoJson',
  mixins: [LayerGroupMixin],
  props: {
    geojson: {
      type: [Object, Array],
      custom: true,
      default: function () { return ({}); }
    },
    options: {
      type: Object,
      custom: true,
      default: function () { return ({}); }
    },
    optionsStyle: {
      type: [Object, Function],
      custom: true,
      default: null
    }
  },
  computed: {
    mergedOptions: function mergedOptions () {
      return optionsMerger(Object.assign({}, this.layerGroupOptions,
        {style: this.optionsStyle}), this);
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    this.mapObject = leaflet.geoJSON(this.geojson, this.mergedOptions);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.parentContainer = findRealParent(this.$parent, true);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  beforeDestroy: function beforeDestroy () {
    this.parentContainer.mapObject.removeLayer(this.mapObject);
  },
  methods: {
    setGeojson: function setGeojson (newVal) {
      this.mapObject.clearLayers();
      this.mapObject.addData(newVal);
    },
    getGeoJSONData: function getGeoJSONData () {
      return this.mapObject.toGeoJSON();
    },
    getBounds: function getBounds () {
      return this.mapObject.getBounds();
    },
    setOptions: function setOptions$1 (newVal, oldVal) {
      this.mapObject.clearLayers();
      leaflet.setOptions(this.mapObject, this.mergedOptions);
      this.mapObject.addData(this.geojson);
    },
    setOptionsStyle: function setOptionsStyle (newVal, oldVal) {
      this.mapObject.setStyle(newVal);
    }
  },
  render: function render () {
    return null;
  }
};

/* script */
var __vue_script__$8 = script$8;

/* template */

  /* style */
  var __vue_inject_styles__$8 = undefined;
  /* scoped */
  var __vue_scope_id__$8 = undefined;
  /* module identifier */
  var __vue_module_identifier__$8 = undefined;
  /* functional template */
  var __vue_is_functional_template__$8 = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LGeoJson = normalizeComponent_1(
    {},
    __vue_inject_styles__$8,
    __vue_script__$8,
    __vue_scope_id__$8,
    __vue_is_functional_template__$8,
    __vue_module_identifier__$8,
    undefined,
    undefined
  );

//

var script$9 = {
  name: 'LGridLayer',
  mixins: [GridLayerMixin, Options],

  props: {
    tileComponent: {
      type: Object,
      custom: true,
      required: true
    }
  },

  data: function data () {
    return {
      tileComponents: {}
    };
  },

  computed: {
    TileConstructor: function TileConstructor () {
      return Vue.extend(this.tileComponent);
    }
  },

  mounted: function mounted () {
    var this$1 = this;

    var GLayer = leaflet.GridLayer.extend({});
    var options = optionsMerger(this.gridLayerOptions, this);
    this.mapObject = new GLayer(options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    this.mapObject.on('tileunload', this.onUnload, this);
    propsBinder(this, this.mapObject, this.$options.props);
    this.mapObject.createTile = this.createTile;
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  beforeDestroy: function beforeDestroy () {
    this.parentContainer.removeLayer(this.mapObject);
    this.mapObject.off('tileunload', this.onUnload);
    this.mapObject = null;
  },

  methods: {
    createTile: function createTile (coords) {
      var div = leaflet.DomUtil.create('div');
      var dummy = leaflet.DomUtil.create('div');
      div.appendChild(dummy);

      var tileInstance = new this.TileConstructor({
        el: dummy,
        parent: this,
        propsData: {
          coords: coords
        }
      });

      var key = this.mapObject._tileCoordsToKey(coords);
      this.tileComponents[key] = tileInstance;

      return div;
    },

    onUnload: function onUnload (e) {
      var key = this.mapObject._tileCoordsToKey(e.coords);
      if (typeof this.tileComponents[key] !== 'undefined') {
        this.tileComponents[key].$destroy();
        this.tileComponents[key].$el.remove();
        delete this.tileComponents[key];
      }
    },

    setTileComponent: function setTileComponent (newVal) {
      this.mapObject.redraw();
    }
  }
};

/* script */
var __vue_script__$9 = script$9;

/* template */
var __vue_render__$4 = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div')};
var __vue_staticRenderFns__$4 = [];

  /* style */
  var __vue_inject_styles__$9 = undefined;
  /* scoped */
  var __vue_scope_id__$9 = undefined;
  /* module identifier */
  var __vue_module_identifier__$9 = undefined;
  /* functional template */
  var __vue_is_functional_template__$9 = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LGridLayer = normalizeComponent_1(
    { render: __vue_render__$4, staticRenderFns: __vue_staticRenderFns__$4 },
    __vue_inject_styles__$9,
    __vue_script__$9,
    __vue_scope_id__$9,
    __vue_is_functional_template__$9,
    __vue_module_identifier__$9,
    undefined,
    undefined
  );

//

var script$a = {
  name: 'LIcon',
  props: {
    iconUrl: {
      type: String,
      custom: true,
      default: null
    },
    iconRetinaUrl: {
      type: String,
      custom: true,
      default: null
    },
    iconSize: {
      type: [Object, Array],
      custom: true,
      default: null
    },
    iconAnchor: {
      type: [Object, Array],
      custom: true,
      default: null
    },
    popupAnchor: {
      type: [Object, Array],
      custom: true,
      default: function () { return [0, 0]; }
    },
    tooltipAnchor: {
      type: [Object, Array],
      custom: true,
      default: function () { return [0, 0]; }
    },
    shadowUrl: {
      type: String,
      custom: true,
      default: null
    },
    shadowRetinaUrl: {
      type: String,
      custom: true,
      default: null
    },
    shadowSize: {
      type: [Object, Array],
      custom: true,
      default: null
    },
    shadowAnchor: {
      type: [Object, Array],
      custom: true,
      default: null
    },
    bgPos: {
      type: [Object, Array],
      custom: true,
      default: function () { return [0, 0]; }
    },
    className: {
      type: String,
      custom: true,
      default: ''
    },
    options: {
      type: Object,
      custom: true,
      default: function () { return ({}); }
    }
  },

  data: function data () {
    return {
      parentContainer: null,
      observer: null,
      recreationNeeded: false,
      swapHtmlNeeded: false
    };
  },

  mounted: function mounted () {
    var this$1 = this;

    this.parentContainer = findRealParent(this.$parent);

    propsBinder(this, this.$parent.mapObject, this.$options.props);

    this.observer = new MutationObserver(function () {
      this$1.scheduleHtmlSwap();
    });
    this.observer.observe(
      this.$el,
      { attributes: true, childList: true, characterData: true, subtree: true }
    );
    this.scheduleCreateIcon();
  },

  beforeDestroy: function beforeDestroy () {
    if (this.parentContainer.mapObject) {
      this.parentContainer.mapObject.setIcon(this.parentContainer.$props.icon);
    }

    this.observer.disconnect();
  },

  methods: {
    scheduleCreateIcon: function scheduleCreateIcon () {
      this.recreationNeeded = true;

      this.$nextTick(this.createIcon);
    },

    scheduleHtmlSwap: function scheduleHtmlSwap () {
      this.htmlSwapNeeded = true;

      this.$nextTick(this.createIcon);
    },

    createIcon: function createIcon () {
      // If only html of a divIcon changed, we can just replace the DOM without the need of recreating the whole icon
      if (this.htmlSwapNeeded && !this.recreationNeeded && this.iconObject && this.parentContainer.mapObject.getElement()) {
        this.parentContainer.mapObject.getElement().innerHTML = this.$el.innerHTML;

        this.htmlSwapNeeded = false;
        return;
      }

      if (!this.recreationNeeded) {
        return;
      }

      if (this.iconObject) {
        leaflet.DomEvent.off(this.iconObject, this.$listeners);
      }

      var options = optionsMerger({
        iconUrl: this.iconUrl,
        iconRetinaUrl: this.iconRetinaUrl,
        iconSize: this.iconSize,
        iconAnchor: this.iconAnchor,
        popupAnchor: this.popupAnchor,
        tooltipAnchor: this.tooltipAnchor,
        shadowUrl: this.shadowUrl,
        shadowRetinaUrl: this.shadowRetinaUrl,
        shadowSize: this.shadowSize,
        shadowAnchor: this.shadowAnchor,
        bgPos: this.bgPos,
        className: this.className,
        html: this.$el.innerHTML || this.html
      }, this);

      if (options.html) {
        this.iconObject = leaflet.divIcon(options);
      } else {
        this.iconObject = leaflet.icon(options);
      }

      leaflet.DomEvent.on(this.iconObject, this.$listeners);

      this.parentContainer.mapObject.setIcon(this.iconObject);

      this.recreationNeeded = false;
      this.htmlSwapNeeded = false;
    },

    setIconUrl: function setIconUrl () {
      this.scheduleCreateIcon();
    },
    setIconRetinaUrl: function setIconRetinaUrl () {
      this.scheduleCreateIcon();
    },
    setIconSize: function setIconSize () {
      this.scheduleCreateIcon();
    },
    setIconAnchor: function setIconAnchor () {
      this.scheduleCreateIcon();
    },
    setPopupAnchor: function setPopupAnchor () {
      this.scheduleCreateIcon();
    },
    setTooltipAnchor: function setTooltipAnchor () {
      this.scheduleCreateIcon();
    },
    setShadowUrl: function setShadowUrl () {
      this.scheduleCreateIcon();
    },
    setShadowRetinaUrl: function setShadowRetinaUrl () {
      this.scheduleCreateIcon();
    },
    setShadowAnchor: function setShadowAnchor () {
      this.scheduleCreateIcon();
    },
    setBgPos: function setBgPos () {
      this.scheduleCreateIcon();
    },
    setClassName: function setClassName () {
      this.scheduleCreateIcon();
    },
    setHtml: function setHtml () {
      this.scheduleCreateIcon();
    }
  },

  render: function render () {
    return null;
  }
};

/* script */
var __vue_script__$a = script$a;

/* template */
var __vue_render__$5 = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',[_vm._t("default")],2)};
var __vue_staticRenderFns__$5 = [];

  /* style */
  var __vue_inject_styles__$a = undefined;
  /* scoped */
  var __vue_scope_id__$a = undefined;
  /* module identifier */
  var __vue_module_identifier__$a = undefined;
  /* functional template */
  var __vue_is_functional_template__$a = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LIcon = normalizeComponent_1(
    { render: __vue_render__$5, staticRenderFns: __vue_staticRenderFns__$5 },
    __vue_inject_styles__$a,
    __vue_script__$a,
    __vue_scope_id__$a,
    __vue_is_functional_template__$a,
    __vue_module_identifier__$a,
    undefined,
    undefined
  );

var script$b = {
  name: 'LIconDefault',
  props: {
    imagePath: {
      type: String,
      custom: true,
      default: ''
    }
  },
  mounted: function mounted () {
    leaflet.Icon.Default.imagePath = this.imagePath;
    propsBinder(this, {}, this.$options.props);
  },
  methods: {
    setImagePath: function setImagePath (newVal) {
      leaflet.Icon.Default.imagePath = newVal;
    }
  },
  render: function render () {
    return null;
  }
};

/* script */
var __vue_script__$b = script$b;

/* template */

  /* style */
  var __vue_inject_styles__$b = undefined;
  /* scoped */
  var __vue_scope_id__$b = undefined;
  /* module identifier */
  var __vue_module_identifier__$b = undefined;
  /* functional template */
  var __vue_is_functional_template__$b = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LIconDefault = normalizeComponent_1(
    {},
    __vue_inject_styles__$b,
    __vue_script__$b,
    __vue_scope_id__$b,
    __vue_is_functional_template__$b,
    __vue_module_identifier__$b,
    undefined,
    undefined
  );

var script$c = {
  name: 'LImageOverlay',
  mixins: [ImageOverlayMixin],
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.imageOverlayOptions, this);
    this.mapObject = leaflet.imageOverlay(this.url, this.bounds, options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  render: function render () {
    return null;
  }
};

/* script */
var __vue_script__$c = script$c;

/* template */

  /* style */
  var __vue_inject_styles__$c = undefined;
  /* scoped */
  var __vue_scope_id__$c = undefined;
  /* module identifier */
  var __vue_module_identifier__$c = undefined;
  /* functional template */
  var __vue_is_functional_template__$c = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LImageOverlay = normalizeComponent_1(
    {},
    __vue_inject_styles__$c,
    __vue_script__$c,
    __vue_scope_id__$c,
    __vue_is_functional_template__$c,
    __vue_module_identifier__$c,
    undefined,
    undefined
  );

//

var script$d = {
  name: 'LLayerGroup',
  mixins: [LayerGroupMixin],
  data: function data () {
    return {
      ready: false
    };
  },
  mounted: function mounted () {
    var this$1 = this;

    this.mapObject = leaflet.layerGroup();
    propsBinder(this, this.mapObject, this.$options.props);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    this.ready = true;
    this.parentContainer = findRealParent(this.$parent);
    if (this.visible) {
      this.parentContainer.addLayer(this);
    }
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  }
};

/* script */
var __vue_script__$d = script$d;

/* template */
var __vue_render__$6 = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',{staticStyle:{"display":"none"}},[(_vm.ready)?_vm._t("default"):_vm._e()],2)};
var __vue_staticRenderFns__$6 = [];

  /* style */
  var __vue_inject_styles__$d = undefined;
  /* scoped */
  var __vue_scope_id__$d = undefined;
  /* module identifier */
  var __vue_module_identifier__$d = undefined;
  /* functional template */
  var __vue_is_functional_template__$d = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LLayerGroup = normalizeComponent_1(
    { render: __vue_render__$6, staticRenderFns: __vue_staticRenderFns__$6 },
    __vue_inject_styles__$d,
    __vue_script__$d,
    __vue_scope_id__$d,
    __vue_is_functional_template__$d,
    __vue_module_identifier__$d,
    undefined,
    undefined
  );

//

var script$e = {
  name: 'LMap',
  mixins: [Options],
  props: {
    center: {
      type: [Object, Array],
      custom: true,
      default: function () { return [0, 0]; }
    },
    bounds: {
      type: [Array, Object],
      custom: true,
      default: null
    },
    maxBounds: {
      type: [Array, Object],
      default: null
    },
    zoom: {
      type: Number,
      custom: true,
      default: 0
    },
    minZoom: {
      type: Number,
      default: null
    },
    maxZoom: {
      type: Number,
      default: null
    },
    paddingBottomRight: {
      type: Array,
      custom: true,
      default: null
    },
    paddingTopLeft: {
      type: Array,
      custom: true,
      default: null
    },
    padding: {
      type: Array,
      custom: true,
      default: null
    },
    worldCopyJump: {
      type: Boolean,
      default: false
    },
    crs: {
      type: Object,
      custom: true,
      default: function () { return leaflet.CRS.EPSG3857; }
    },
    maxBoundsViscosity: {
      type: Number,
      default: null
    },
    inertia: {
      type: Boolean,
      default: null
    },
    inertiaDeceleration: {
      type: Number,
      default: null
    },
    inertiaMaxSpeed: {
      type: Number,
      default: null
    },
    easeLinearity: {
      type: Number,
      default: null
    },
    zoomAnimation: {
      type: Boolean,
      default: null
    },
    zoomAnimationThreshold: {
      type: Number,
      default: null
    },
    fadeAnimation: {
      type: Boolean,
      default: null
    },
    markerZoomAnimation: {
      type: Boolean,
      default: null
    },
    noBlockingAnimations: {
      type: Boolean,
      default: false
    }
  },
  data: function data () {
    return {
      ready: false,
      lastSetCenter: null,
      lastSetBounds: null,
      lastSetZoom: null,
      layerControl: undefined,
      layersToAdd: []
    };
  },
  computed: {
    fitBoundsOptions: function fitBoundsOptions () {
      var options = {};
      if (this.padding) {
        options.padding = this.padding;
      } else {
        if (this.paddingBottomRight) {
          options.paddingBottomRight = this.paddingBottomRight;
        }
        if (this.paddingTopLeft) {
          options.paddingTopLeft = this.paddingTopLeft;
        }
      }
      return options;
    }
  },
  beforeDestroy: function beforeDestroy () {
    if (this.mapObject) {
      this.mapObject.remove();
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger({
      minZoom: this.minZoom,
      maxZoom: this.maxZoom,
      maxBounds: this.maxBounds,
      maxBoundsViscosity: this.maxBoundsViscosity,
      worldCopyJump: this.worldCopyJump,
      crs: this.crs,
      center: this.center,
      zoom: this.zoom,
      inertia: this.inertia,
      inertiaDeceleration: this.inertiaDeceleration,
      inertiaMaxSpeed: this.inertiaMaxSpeed,
      easeLinearity: this.easeLinearity,
      zoomAnimation: this.zoomAnimation,
      zoomAnimationThreshold: this.zoomAnimationThreshold,
      fadeAnimation: this.fadeAnimation,
      markerZoomAnimation: this.markerZoomAnimation
    }, this);
    this.mapObject = leaflet.map(this.$el, options);
    this.setBounds(this.bounds);
    this.mapObject.on('moveend', debounce(this.moveEndHandler, 100));
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.ready = true;
    // DEPRECATED leaflet:load
    this.$emit('leaflet:load');
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  methods: {
    registerLayerControl: function registerLayerControl (lControlLayers) {
      var this$1 = this;

      this.layerControl = lControlLayers;
      this.mapObject.addControl(lControlLayers.mapObject);
      this.layersToAdd.forEach(function (layer) {
        this$1.layerControl.addLayer(layer);
      });
      this.layersToAdd = [];
    },
    addLayer: function addLayer (layer, alreadyAdded) {
      if (layer.layerType !== undefined) {
        if (this.layerControl === undefined) {
          this.layersToAdd.push(layer);
        } else {
          this.layerControl.addLayer(layer);
        }
      }
      if (!alreadyAdded) {
        this.mapObject.addLayer(layer.mapObject);
      }
    },
    removeLayer: function removeLayer (layer, alreadyRemoved) {
      if (layer.layerType !== undefined) {
        if (this.layerControl === undefined) {
          this.layersToAdd = this.layersToAdd.filter(function (l) { return l.name !== layer.name; });
        } else {
          this.layerControl.removeLayer(layer);
        }
      }
      if (!alreadyRemoved) {
        this.mapObject.removeLayer(layer.mapObject);
      }
    },
    setZoom: function setZoom (newVal, oldVal) {
      this.mapObject.setZoom(newVal, {
        animate: !this.noBlockingAnimations ? false : null
      });
    },
    setCenter: function setCenter (newVal, oldVal) {
      if (newVal == null) {
        return;
      }
      var newCenter = leaflet.latLng(newVal);
      var oldCenter = this.lastSetCenter || this.mapObject.getCenter();
      if (oldCenter.lat !== newCenter.lat ||
        oldCenter.lng !== newCenter.lng) {
        this.lastSetCenter = newCenter;
        this.mapObject.panTo(newCenter, {
          animate: !this.noBlockingAnimations ? false : null
        });
      }
    },
    setBounds: function setBounds (newVal, oldVal) {
      if (!newVal) {
        return;
      }
      var newBounds = leaflet.latLngBounds(newVal);
      if (!newBounds.isValid()) {
        return;
      }
      var oldBounds = this.lastSetBounds || this.mapObject.getBounds();
      var boundsChanged = !oldBounds.equals(newBounds, 0); // set maxMargin to 0 - check exact equals
      if (boundsChanged) {
        this.lastSetBounds = newBounds;
        this.mapObject.fitBounds(newBounds, this.fitBoundsOptions);
      }
    },
    setPaddingBottomRight: function setPaddingBottomRight (newVal, oldVal) {
      this.paddingBottomRight = newVal;
    },
    setPaddingTopLeft: function setPaddingTopLeft (newVal, oldVal) {
      this.paddingTopLeft = newVal;
    },
    setPadding: function setPadding (newVal, oldVal) {
      this.padding = newVal;
    },
    setCrs: function setCrs (newVal, oldVal) {
      console.log('Changing CRS is not yet supported by Leaflet');
    },
    fitBounds: function fitBounds (bounds) {
      this.mapObject.fitBounds(bounds);
    },
    moveEndHandler: function moveEndHandler () {
      this.$emit('update:zoom', this.mapObject.getZoom());
      var center = this.mapObject.getCenter();
      this.$emit('update:center', center);
      var bounds = this.mapObject.getBounds();
      this.$emit('update:bounds', bounds);
    }
  }
};

var isOldIE = typeof navigator !== 'undefined' && /msie [6-9]\\b/.test(navigator.userAgent.toLowerCase());
function createInjector(context) {
  return function (id, style) {
    return addStyle(id, style);
  };
}
var HEAD = document.head || document.getElementsByTagName('head')[0];
var styles = {};

function addStyle(id, css) {
  var group = isOldIE ? css.media || 'default' : id;
  var style = styles[group] || (styles[group] = {
    ids: new Set(),
    styles: []
  });

  if (!style.ids.has(id)) {
    style.ids.add(id);
    var code = css.source;

    if (css.map) {
      // https://developer.chrome.com/devtools/docs/javascript-debugging
      // this makes source maps inside style tags work properly in Chrome
      code += '\n/*# sourceURL=' + css.map.sources[0] + ' */'; // http://stackoverflow.com/a/26603875

      code += '\n/*# sourceMappingURL=data:application/json;base64,' + btoa(unescape(encodeURIComponent(JSON.stringify(css.map)))) + ' */';
    }

    if (!style.element) {
      style.element = document.createElement('style');
      style.element.type = 'text/css';
      if (css.media) { style.element.setAttribute('media', css.media); }
      HEAD.appendChild(style.element);
    }

    if ('styleSheet' in style.element) {
      style.styles.push(code);
      style.element.styleSheet.cssText = style.styles.filter(Boolean).join('\n');
    } else {
      var index = style.ids.size - 1;
      var textNode = document.createTextNode(code);
      var nodes = style.element.childNodes;
      if (nodes[index]) { style.element.removeChild(nodes[index]); }
      if (nodes.length) { style.element.insertBefore(textNode, nodes[index]); }else { style.element.appendChild(textNode); }
    }
  }
}

var browser = createInjector;

/* script */
var __vue_script__$e = script$e;

/* template */
var __vue_render__$7 = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',{staticClass:"vue2leaflet-map"},[(_vm.ready)?_vm._t("default"):_vm._e()],2)};
var __vue_staticRenderFns__$7 = [];

  /* style */
  var __vue_inject_styles__$e = function (inject) {
    if (!inject) { return }
    inject("data-v-2935624e_0", { source: ".vue2leaflet-map{height:100%;width:100%}", map: undefined, media: undefined });

  };
  /* scoped */
  var __vue_scope_id__$e = undefined;
  /* module identifier */
  var __vue_module_identifier__$e = undefined;
  /* functional template */
  var __vue_is_functional_template__$e = false;
  /* style inject SSR */
  

  
  var LMap = normalizeComponent_1(
    { render: __vue_render__$7, staticRenderFns: __vue_staticRenderFns__$7 },
    __vue_inject_styles__$e,
    __vue_script__$e,
    __vue_scope_id__$e,
    __vue_is_functional_template__$e,
    __vue_module_identifier__$e,
    browser,
    undefined
  );

var script$f = {
  name: 'LMarker',
  mixins: [Layer, Options],
  props: {
    pane: {
      type: String,
      default: 'markerPane'
    },
    draggable: {
      type: Boolean,
      custom: true,
      default: false
    },
    latLng: {
      type: [Object, Array],
      custom: true,
      default: null
    },
    icon: {
      type: [Object],
      custom: false,
      default: function () { return new leaflet.Icon.Default(); }
    },
    zIndexOffset: {
      type: Number,
      custom: false,
      default: null
    }
  },
  data: function data () {
    return {
      ready: false
    };
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(Object.assign({}, this.layerOptions,
      {icon: this.icon,
      zIndexOffset: this.zIndexOffset,
      draggable: this.draggable}), this);
    this.mapObject = leaflet.marker(this.latLng, options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    this.mapObject.on('move', debounce(this.latLngSync, 100));
    propsBinder(this, this.mapObject, this.$options.props);
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.ready = true;
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  methods: {
    setDraggable: function setDraggable (newVal, oldVal) {
      if (this.mapObject.dragging) {
        newVal ? this.mapObject.dragging.enable() : this.mapObject.dragging.disable();
      }
    },
    setLatLng: function setLatLng (newVal) {
      if (newVal == null) {
        return;
      }

      if (this.mapObject) {
        var oldLatLng = this.mapObject.getLatLng();
        var newLatLng = leaflet.latLng(newVal);
        if (newLatLng.lat !== oldLatLng.lat || newLatLng.lng !== oldLatLng.lng) {
          this.mapObject.setLatLng(newLatLng);
        }
      }
    },
    latLngSync: function latLngSync (event) {
      this.$emit('update:latLng', event.latlng);
      this.$emit('update:lat-lng', event.latlng);
    }
  },
  render: function (h) {
    if (this.ready && this.$slots.default) {
      return h('div', { style: { display: 'none' } }, this.$slots.default);
    }
    return null;
  }
};

/* script */
var __vue_script__$f = script$f;

/* template */

  /* style */
  var __vue_inject_styles__$f = undefined;
  /* scoped */
  var __vue_scope_id__$f = undefined;
  /* module identifier */
  var __vue_module_identifier__$f = undefined;
  /* functional template */
  var __vue_is_functional_template__$f = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LMarker = normalizeComponent_1(
    {},
    __vue_inject_styles__$f,
    __vue_script__$f,
    __vue_scope_id__$f,
    __vue_is_functional_template__$f,
    __vue_module_identifier__$f,
    undefined,
    undefined
  );

//

var script$g = {
  name: 'LPolygon',
  mixins: [Polygon],
  props: {
    latLngs: {
      type: Array,
      default: function () { return []; }
    }
  },
  data: function data () {
    return {
      ready: false
    };
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.polygonOptions, this);
    this.mapObject = leaflet.polygon(this.latLngs, options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.ready = true;
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  }
};

/* script */
var __vue_script__$g = script$g;

/* template */
var __vue_render__$8 = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',{staticStyle:{"display":"none"}},[(_vm.ready)?_vm._t("default"):_vm._e()],2)};
var __vue_staticRenderFns__$8 = [];

  /* style */
  var __vue_inject_styles__$g = undefined;
  /* scoped */
  var __vue_scope_id__$g = undefined;
  /* module identifier */
  var __vue_module_identifier__$g = undefined;
  /* functional template */
  var __vue_is_functional_template__$g = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LPolygon = normalizeComponent_1(
    { render: __vue_render__$8, staticRenderFns: __vue_staticRenderFns__$8 },
    __vue_inject_styles__$g,
    __vue_script__$g,
    __vue_scope_id__$g,
    __vue_is_functional_template__$g,
    __vue_module_identifier__$g,
    undefined,
    undefined
  );

//

var script$h = {
  name: 'LPolyline',
  mixins: [PolylineMixin],
  props: {
    latLngs: {
      type: Array,
      default: function () { return []; }
    }
  },
  data: function data () {
    return {
      ready: false
    };
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.polyLineOptions, this);
    this.mapObject = leaflet.polyline(this.latLngs, options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.ready = true;
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  }
};

/* script */
var __vue_script__$h = script$h;

/* template */
var __vue_render__$9 = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',{staticStyle:{"display":"none"}},[(_vm.ready)?_vm._t("default"):_vm._e()],2)};
var __vue_staticRenderFns__$9 = [];

  /* style */
  var __vue_inject_styles__$h = undefined;
  /* scoped */
  var __vue_scope_id__$h = undefined;
  /* module identifier */
  var __vue_module_identifier__$h = undefined;
  /* functional template */
  var __vue_is_functional_template__$h = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LPolyline = normalizeComponent_1(
    { render: __vue_render__$9, staticRenderFns: __vue_staticRenderFns__$9 },
    __vue_inject_styles__$h,
    __vue_script__$h,
    __vue_scope_id__$h,
    __vue_is_functional_template__$h,
    __vue_module_identifier__$h,
    undefined,
    undefined
  );

var script$i = {
  name: 'LPopup',
  mixins: [Popper, Options],
  props: {
    latLng: {
      type: [Object, Array],
      default: function () { return []; }
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.popperOptions, this);
    this.mapObject = leaflet.popup(options);
    if (this.latLng !== undefined) {
      this.mapObject.setLatLng(this.latLng);
    }
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.mapObject.setContent(this.content || this.$el);
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.mapObject.bindPopup(this.mapObject);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  beforeDestroy: function beforeDestroy () {
    if (this.parentContainer) {
      if (this.parentContainer.unbindPopup) {
        this.parentContainer.unbindPopup();
      } else if (this.parentContainer.mapObject && this.parentContainer.mapObject.unbindPopup) {
        this.parentContainer.mapObject.unbindPopup();
      }
    }
  }
};

/* script */
var __vue_script__$i = script$i;

/* template */

  /* style */
  var __vue_inject_styles__$i = undefined;
  /* scoped */
  var __vue_scope_id__$i = undefined;
  /* module identifier */
  var __vue_module_identifier__$i = undefined;
  /* functional template */
  var __vue_is_functional_template__$i = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LPopup = normalizeComponent_1(
    {},
    __vue_inject_styles__$i,
    __vue_script__$i,
    __vue_scope_id__$i,
    __vue_is_functional_template__$i,
    __vue_module_identifier__$i,
    undefined,
    undefined
  );

//

var script$j = {
  name: 'LRectangle',
  mixins: [Polygon],
  props: {
    bounds: {
      type: Array,
      default: function () { return []; }
    }
  },
  data: function data () {
    return {
      ready: false
    };
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.polygonOptions, this);
    this.mapObject = leaflet.rectangle(this.bounds, options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.ready = true;
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  }
};

/* script */
var __vue_script__$j = script$j;

/* template */
var __vue_render__$a = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',{staticStyle:{"display":"none"}},[(_vm.ready)?_vm._t("default"):_vm._e()],2)};
var __vue_staticRenderFns__$a = [];

  /* style */
  var __vue_inject_styles__$j = undefined;
  /* scoped */
  var __vue_scope_id__$j = undefined;
  /* module identifier */
  var __vue_module_identifier__$j = undefined;
  /* functional template */
  var __vue_is_functional_template__$j = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LRectangle = normalizeComponent_1(
    { render: __vue_render__$a, staticRenderFns: __vue_staticRenderFns__$a },
    __vue_inject_styles__$j,
    __vue_script__$j,
    __vue_scope_id__$j,
    __vue_is_functional_template__$j,
    __vue_module_identifier__$j,
    undefined,
    undefined
  );

//

var script$k = {
  name: 'LTileLayer',
  mixins: [TileLayerMixin, Options],
  props: {
    url: {
      type: String,
      default: null
    },
    tileLayerClass: {
      type: Function,
      default: leaflet.tileLayer
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.tileLayerOptions, this);
    this.mapObject = this.tileLayerClass(this.url, options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  }
};

/* script */
var __vue_script__$k = script$k;

/* template */
var __vue_render__$b = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div')};
var __vue_staticRenderFns__$b = [];

  /* style */
  var __vue_inject_styles__$k = undefined;
  /* scoped */
  var __vue_scope_id__$k = undefined;
  /* module identifier */
  var __vue_module_identifier__$k = undefined;
  /* functional template */
  var __vue_is_functional_template__$k = false;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LTileLayer = normalizeComponent_1(
    { render: __vue_render__$b, staticRenderFns: __vue_staticRenderFns__$b },
    __vue_inject_styles__$k,
    __vue_script__$k,
    __vue_scope_id__$k,
    __vue_is_functional_template__$k,
    __vue_module_identifier__$k,
    undefined,
    undefined
  );

var script$l = {
  name: 'LTooltip',
  mixins: [Popper, Options],
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.popperOptions, this);
    this.mapObject = leaflet.tooltip(options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.mapObject.setContent(this.content || this.$el);
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.mapObject.bindTooltip(this.mapObject);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  beforeDestroy: function beforeDestroy () {
    if (this.parentContainer) {
      if (this.parentContainer.unbindTooltip) {
        this.parentContainer.unbindTooltip();
      } else if (this.parentContainer.mapObject && this.parentContainer.mapObject.unbindTooltip) {
        this.parentContainer.mapObject.unbindTooltip();
      }
    }
  }
};

/* script */
var __vue_script__$l = script$l;

/* template */

  /* style */
  var __vue_inject_styles__$l = undefined;
  /* scoped */
  var __vue_scope_id__$l = undefined;
  /* module identifier */
  var __vue_module_identifier__$l = undefined;
  /* functional template */
  var __vue_is_functional_template__$l = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LTooltip = normalizeComponent_1(
    {},
    __vue_inject_styles__$l,
    __vue_script__$l,
    __vue_scope_id__$l,
    __vue_is_functional_template__$l,
    __vue_module_identifier__$l,
    undefined,
    undefined
  );

var script$m = {
  name: 'LWMSTileLayer',
  mixins: [TileLayerWMS, Options],
  props: {
    baseUrl: {
      type: String,
      default: null
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger(this.tileLayerWMSOptions, this);
    this.mapObject = leaflet.tileLayer.wms(this.baseUrl, options);
    leaflet.DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.parentContainer = findRealParent(this.$parent);
    this.parentContainer.addLayer(this, !this.visible);
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  }
};

/* script */
var __vue_script__$m = script$m;

/* template */

  /* style */
  var __vue_inject_styles__$m = undefined;
  /* scoped */
  var __vue_scope_id__$m = undefined;
  /* module identifier */
  var __vue_module_identifier__$m = undefined;
  /* functional template */
  var __vue_is_functional_template__$m = undefined;
  /* style inject */
  
  /* style inject SSR */
  

  
  var LWMSTileLayer = normalizeComponent_1(
    {},
    __vue_inject_styles__$m,
    __vue_script__$m,
    __vue_scope_id__$m,
    __vue_is_functional_template__$m,
    __vue_module_identifier__$m,
    undefined,
    undefined
  );

exports.CircleMixin = CircleMixin;
exports.ControlMixin = ControlMixin;
exports.GridLayerMixin = GridLayerMixin;
exports.ImageOverlayMixin = ImageOverlayMixin;
exports.InteractiveLayerMixin = InteractiveLayer;
exports.LayerMixin = Layer;
exports.LayerGroupMixin = LayerGroupMixin;
exports.OptionsMixin = Options;
exports.PathMixin = Path;
exports.PolygonMixin = Polygon;
exports.PolylineMixin = PolylineMixin;
exports.PopperMixin = Popper;
exports.TileLayerMixin = TileLayerMixin;
exports.TileLayerWMSMixin = TileLayerWMS;
exports.LCircle = LCircle;
exports.LCircleMarker = LCircleMarker;
exports.LControl = LControl;
exports.LControlAttribution = LControlAttribution;
exports.LControlLayers = LControlLayers;
exports.LControlScale = LControlScale;
exports.LControlZoom = LControlZoom;
exports.LFeatureGroup = LFeatureGroup;
exports.LGeoJson = LGeoJson;
exports.LGridLayer = LGridLayer;
exports.LIcon = LIcon;
exports.LIconDefault = LIconDefault;
exports.LImageOverlay = LImageOverlay;
exports.LLayerGroup = LLayerGroup;
exports.LMap = LMap;
exports.LMarker = LMarker;
exports.LPolygon = LPolygon;
exports.LPolyline = LPolyline;
exports.LPopup = LPopup;
exports.LRectangle = LRectangle;
exports.LTileLayer = LTileLayer;
exports.LTooltip = LTooltip;
exports.LWMSTileLayer = LWMSTileLayer;
exports.debounce = debounce;
exports.capitalizeFirstLetter = capitalizeFirstLetter;
exports.propsBinder = propsBinder;
exports.collectionCleaner = collectionCleaner;
exports.optionsMerger = optionsMerger;
exports.findRealParent = findRealParent;
