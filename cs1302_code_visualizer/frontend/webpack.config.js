const path = require("path");
const webpack = require("webpack");

module.exports = (env, argv) => {
  const mode = argv.mode || "production";
  return {
    mode: mode,
    devtool: mode === "production" ? "source-map" : "eval-source-map",
    plugins: [
      new webpack.ProvidePlugin({
        jquery: "jquery",
        jQuery: "jquery",
        $: "jquery",
      }),
    ],

    resolve: {
      extensions: [".ts", ".js", ".css"],
    },

    entry: {
      "render-trace": "./js/render-trace.ts",
      "vis-module": "./js/CodeVisualizer.ts",
    },

    output: {
      path: path.resolve(__dirname, "build"),
      filename: "[name].bundle.js",
      sourceMapFilename: "[file].map",
      library: {
        name: "CodeVisualizer",
        type: "umd",
      },
    },

    module: {
      rules: [
        { test: /\.css$/, use: ["style-loader", "css-loader"] },
        { test: /\.(png|jpg|jpeg|gif)$/i, type: "asset/inline" },
        { test: /\.ts$/, use: "ts-loader" },
      ],
    },
  };
};
